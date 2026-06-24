from __future__ import annotations

import builtins
from typing import Any

_orig_import = builtins.__import__
_installed = False


def patch_qwen2_tokenizer() -> None:
    try:
        from transformers.models.qwen2.tokenization_qwen2 import Qwen2Tokenizer
    except Exception:
        return
    if hasattr(Qwen2Tokenizer, "all_special_tokens_extended"):
        return
    Qwen2Tokenizer.all_special_tokens_extended = property(  # type: ignore[attr-defined]
        lambda self: list(self.all_special_tokens)
    )


def _patched_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] | None = (),
    level: int = 0,
):
    module = _orig_import(name, globals, locals, fromlist, level)
    if name.startswith("transformers") or (
        fromlist is not None and "transformers" in fromlist
    ):
        patch_qwen2_tokenizer()
    return module


def install_qwen2_tokenizer_compat() -> None:
    global _installed
    if _installed:
        return
    builtins.__import__ = _patched_import
    _installed = True
    patch_qwen2_tokenizer()


install_qwen2_tokenizer_compat()
