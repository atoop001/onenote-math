"""Registry of candidate handwriting-math recognizers.

Adapters are imported lazily so one model's heavy dependencies don't load
when another is being evaluated.
"""
import importlib
import os
from pathlib import Path

# Keep every downloaded model file inside the project's git-ignored models/ folder
# (on D:), not the user profile on C:. Set before any model library is imported.
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
for _var, _sub in (("HF_HOME", "huggingface"), ("PIX2TEXT_HOME", "pix2text"),
                   ("CNSTD_HOME", "cnstd"), ("CNOCR_HOME", "cnocr"), ("TORCH_HOME", "torch")):
    os.environ[_var] = str(MODEL_DIR / _sub)

_REGISTRY = {
    "pix2text": ("models.pix2text_mfr", "Pix2TextMFR"),
    "texteller": ("models.texteller", "TexTeller"),
}


def get(name: str, weights: str | None = None):
    if name not in _REGISTRY:
        raise KeyError(f"unknown model {name!r}; choose from {', '.join(_REGISTRY)}")
    module, cls = _REGISTRY[name]
    return getattr(importlib.import_module(module), cls)(weights=weights)
