"""TexTeller handwritten/printed math recognizer, PyTorch on CPU."""
_DELIMS = ((r"\[", r"\]"), ("$$", "$$"), (r"\(", r"\)"), ("$", "$"))


def strip_delims(latex: str) -> str:
    s = latex.strip()
    for a, b in _DELIMS:
        if s.startswith(a) and s.endswith(b) and len(s) >= len(a) + len(b):
            return s[len(a):len(s) - len(b)].strip()
    return s


class TexTeller:
    name = "texteller"

    def __init__(self, weights: str | None = None):
        import torch
        from texteller import load_model, load_tokenizer
        self._torch_device = torch.device("cpu")
        self._model = load_model(model_dir=weights)
        self._tok = load_tokenizer()

    def recognize(self, png_path: str) -> str:
        from texteller import img2latex
        return strip_delims(img2latex(self._model, self._tok, [png_path], device=self._torch_device)[0])
