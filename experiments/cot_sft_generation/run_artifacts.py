"""Compatibility shim for CoT SFT artifact helpers."""

try:
    from .core import run_artifacts as _impl
except ImportError:  # pragma: no cover - direct script import path
    from core import run_artifacts as _impl  # type: ignore

for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)

__all__ = [name for name in dir(_impl) if not name.startswith("_")]
