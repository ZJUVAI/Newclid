from __future__ import annotations

import builtins


def _patch_qwen2_tokenizer() -> None:
    try:
        from transformers.models.qwen2.tokenization_qwen2 import Qwen2Tokenizer
    except Exception:
        return
    if hasattr(Qwen2Tokenizer, "all_special_tokens_extended"):
        return
    Qwen2Tokenizer.all_special_tokens_extended = property(  # type: ignore[attr-defined]
        lambda self: list(self.all_special_tokens)
    )


_orig_import = builtins.__import__


def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _orig_import(name, globals, locals, fromlist, level)
    if name.startswith("transformers") or (
        isinstance(fromlist, tuple) and "transformers" in fromlist
    ):
        _patch_qwen2_tokenizer()
    return module


builtins.__import__ = _patched_import
_patch_qwen2_tokenizer()
