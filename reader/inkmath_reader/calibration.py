"""Low-confidence threshold: calibrated on the test set (M4 Task 7), else the default."""
import json
from pathlib import Path

DEFAULT_LOW_THRESHOLD = 0.85
FILE_NAME = "reader_calibration.json"


def low_threshold(models_dir: Path) -> float:
    path = Path(models_dir) / FILE_NAME
    if not path.exists():
        return DEFAULT_LOW_THRESHOLD
    return float(json.loads(path.read_text(encoding="utf-8"))["low_threshold"])
