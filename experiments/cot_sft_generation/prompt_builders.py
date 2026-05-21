"""Compatibility shim for CoT SFT prompt builders."""

try:
    from .core import prompt_builders as _impl
except ImportError:  # pragma: no cover - direct script import path
    from core import prompt_builders as _impl  # type: ignore

for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)

__all__ = [name for name in dir(_impl) if not name.startswith("_")]
