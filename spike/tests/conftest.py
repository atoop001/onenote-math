"""Load PyTorch before anything imports the WinRT ink APIs.

On Windows, importing winrt first makes torch's c10.dll fail to initialize
(WinError 1114). Importing torch first works. Any process that needs both
(the M4 recognizer service) must keep this order.
"""
try:
    import torch  # noqa: F401
except ImportError:
    pass
