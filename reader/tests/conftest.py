import sys
from pathlib import Path

READER = Path(__file__).resolve().parents[1]
REPO = READER.parent
sys.path.insert(0, str(READER))
