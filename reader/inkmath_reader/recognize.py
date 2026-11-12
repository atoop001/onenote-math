"""TexTeller on CPU, with a probability and alternatives for every generated token.

Mirrors texteller.api.inference.img2latex (same preprocessing, generation and
post-processing) but asks generate() for the per-step scores.
"""
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image

_DELIMS = ((r"\[", r"\]"), ("$$", "$$"), (r"\(", r"\)"), ("$", "$"))


def strip_delims(latex: str) -> str:
    s = latex.strip()
    for a, b in _DELIMS:
        if s.startswith(a) and s.endswith(b) and len(s) >= len(a) + len(b):
            return s[len(a):len(s) - len(b)].strip()
    return s


@dataclass
class TokenStep:
    text: str
    prob: float
    alts: list[tuple[str, float]]


@dataclass
class RawReading:
    latex: str                 # final LaTeX, exactly as img2latex would return it
    raw: str                   # concatenated token texts, before post-processing
    steps: list[TokenStep]


def _offline_env(models_dir: Path) -> None:
    os.environ["HF_HOME"] = str(models_dir / "huggingface")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


class Recognizer:
    def __init__(self, models_dir: Path, weights_dir: Path | None = None, max_tokens: int = 256, top_k: int = 5):
        _offline_env(Path(models_dir))
        from texteller import load_model, load_tokenizer
        self.name = "texteller-tuned" if weights_dir else "texteller"
        self.max_tokens, self.top_k = max_tokens, top_k
        self.device = torch.device("cpu")
        self.model = load_model(str(weights_dir) if weights_dir else None).to(self.device).eval()
        self.tokenizer = load_tokenizer(str(weights_dir) if weights_dir else None)

    def read(self, img: Image.Image) -> RawReading:
        from transformers import GenerationConfig
        from texteller.api.format import format_latex
        from texteller.utils import add_newlines, remove_style, transform

        tok = self.tokenizer
        pixel_values = torch.stack(transform([np.array(img.convert("RGB"))]))
        config = GenerationConfig(
            max_new_tokens=self.max_tokens, num_beams=1, do_sample=False,
            pad_token_id=tok.pad_token_id, eos_token_id=tok.eos_token_id, bos_token_id=tok.bos_token_id,
            no_repeat_ngram_size=0,
        )
        with torch.inference_mode():
            out = self.model.generate(pixel_values.to(self.device), generation_config=config,
                                      output_scores=True, return_dict_in_generate=True)
        seq = out.sequences[0]
        new_ids = seq[len(seq) - len(out.scores):]
        special = set(tok.all_special_ids)
        steps = []
        for ids, scores in zip(new_ids.tolist(), out.scores):
            if ids in special:
                if ids == tok.eos_token_id:
                    break
                continue
            probs = torch.softmax(scores[0].float(), dim=-1)
            top = torch.topk(probs, self.top_k)
            alts = [(self._text(i), float(p)) for p, i in zip(top.values.tolist(), top.indices.tolist())
                    if i != ids and i not in special][: self.top_k - 1]
            steps.append(TokenStep(self._text(ids), float(probs[ids]), alts))

        latex = tok.batch_decode(seq.unsqueeze(0), skip_special_tokens=True)[0]
        latex = add_newlines(format_latex(remove_style(latex)))
        return RawReading(strip_delims(latex), "".join(s.text for s in steps), steps)

    def _text(self, token_id: int) -> str:
        return self.tokenizer.convert_tokens_to_string([self.tokenizer.convert_ids_to_tokens(token_id)])
