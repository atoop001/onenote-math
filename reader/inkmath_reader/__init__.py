"""Ink Math handwriting reader: OneNote ink -> LaTeX with per-symbol confidences.

torch must be imported before any WinRT module in the same process, or loading
torch's DLLs fails with WinError 1114 (found in M1). Importing it here, first,
makes every `inkmath_reader.*` import safe.
"""
import torch  # noqa: F401  (import order: see docstring)
