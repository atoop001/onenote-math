"""Pix2Text math-formula recognizer (MFR), ONNX on CPU."""


class Pix2TextMFR:
    name = "pix2text"

    def __init__(self, weights: str | None = None):
        from pix2text import LatexOCR
        kw = {"model_dir": weights} if weights else {}
        self._ocr = LatexOCR(model_backend="onnx", device="cpu", **kw)

    def recognize(self, png_path: str) -> str:
        return self._ocr.recognize(png_path)["text"]
