"""Fine-tune TexTeller on the user's handwriting (dev machine, GPU).

  cd reader
  .venv-train\\Scripts\\python -m train.finetune --out ..\\models\\texteller-tuned

Each epoch sees `--views` augmented renders of every sample. The result is saved with save_pretrained;
train.evaluate then decides whether the reader may use it.
"""
import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch

from inkmath_reader import paths
from inkmath_reader.recognize import _offline_env

from .dataset import augment, load_corrections, load_tune, render_view

MAX_LABEL_TOKENS = 256


def make_labels(tok, latexes: list[str]) -> torch.Tensor:
    """Decoder labels. generate() starts the decoder with bos (decoder_start_token_id), and the model
    shifts labels right behind it, so the tokenizer's own leading bos is dropped. Padding becomes -100."""
    enc = tok(latexes, padding=True, truncation=True, max_length=MAX_LABEL_TOKENS + 1, return_tensors="pt")
    ids = enc.input_ids[:, 1:]
    return ids.masked_fill(ids == tok.pad_token_id, -100)


def _args(argv):
    ap = argparse.ArgumentParser(prog="train.finetune")
    ap.add_argument("--out", default=str(paths.REPO / "models" / "texteller-tuned"))
    ap.add_argument("--models", default=None, help="model files directory (base weights)")
    ap.add_argument("--ink-dir", default=str(paths.REPO / "data" / "ink"))
    ap.add_argument("--prompts", default=str(paths.REPO / "samples" / "prompts_tune.json"))
    ap.add_argument("--corrections", action="append", default=[])
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--views", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=None, help="use only the first N samples (smoke test)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = _args(argv)
    _offline_env(paths.models_dir(a.models))
    from texteller import load_model, load_tokenizer
    from texteller.utils import transform
    from transformers import get_linear_schedule_with_warmup

    random.seed(a.seed)
    torch.manual_seed(a.seed)
    rng = random.Random(a.seed)
    samples = load_tune(Path(a.ink_dir), Path(a.prompts))
    for d in a.corrections:
        samples += load_corrections(Path(d))
    if a.limit:
        samples = samples[: a.limit]
    if not samples:
        print("no tuning samples found", file=sys.stderr)
        return 1

    device = torch.device(a.device)
    model = load_model().to(device).train()
    tok = load_tokenizer()
    # The base config leaves these unset (generate() falls back to bos); training needs them explicitly.
    model.config.decoder_start_token_id = tok.bos_token_id
    model.config.pad_token_id = tok.pad_token_id

    steps_per_epoch = -(-len(samples) * a.views // a.batch)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, min(50, steps_per_epoch * a.epochs // 2), steps_per_epoch * a.epochs)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train_log.txt", "w", encoding="utf-8")
    log.write(f"samples={len(samples)} epochs={a.epochs} lr={a.lr} batch={a.batch} views={a.views} "
              f"seed={a.seed} device={device}\n")
    t0 = time.time()
    for epoch in range(1, a.epochs + 1):
        items = [s for s in samples for _ in range(a.views)]
        rng.shuffle(items)
        losses = []
        for i in range(0, len(items), a.batch):
            chunk = items[i:i + a.batch]
            imgs = [np.array(render_view(augment(s.strokes, rng), rng).convert("RGB")) for s in chunk]
            pv = torch.stack(transform(imgs)).to(device)
            labels = make_labels(tok, [s.latex for s in chunk]).to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                loss = model(pixel_values=pv, labels=labels).loss
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            losses.append(float(loss))
        line = f"epoch {epoch}: loss {sum(losses) / len(losses):.4f} ({time.time() - t0:.0f} s)"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
    log.close()
    model.save_pretrained(out)
    tok.save_pretrained(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
