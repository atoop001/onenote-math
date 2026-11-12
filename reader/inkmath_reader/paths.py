"""Where the reader finds model files and keeps per-user data."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def models_dir(override: str | None = None) -> Path:
    """Model files: the override, else env INKMATH_MODELS, else <repo>/models."""
    if override:
        return Path(override)
    env = os.environ.get("INKMATH_MODELS")
    return Path(env) if env else REPO / "models"


def user_dir() -> Path:
    """Per-user data (snippets, corrections): %LOCALAPPDATA%\\InkMath."""
    return Path(os.environ["LOCALAPPDATA"]) / "InkMath"
