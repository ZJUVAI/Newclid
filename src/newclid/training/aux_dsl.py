"""Helpers for parsing and translating auxiliary-point DSL completions."""

from __future__ import annotations

import re
from typing import Optional

from newclid.evaluation.search_runtime import (
    try_dsl_to_constructions,
    try_full_aux_dsl_to_constructions,
    translate_dsl_to_construction,
)


_AUX_BLOCK_RE = re.compile(r"<aux>\s*(.*?)\s*</aux>", re.DOTALL | re.IGNORECASE)
_AUX_WS_RE = re.compile(r"\s+")


def extract_aux_body(completion: str) -> Optional[str]:
    """Return the first aux block body or fall back to the raw completion text."""
    if completion is None:
        return None

    text = str(completion).strip()
    if not text:
        return None

    match = _AUX_BLOCK_RE.search(text)
    body = match.group(1) if match else text
    body = body.strip()
    if not body:
        return None

    # Preserve the leading x00 marker so training targets keep the same
    # format as the model's response prefix.
    return body or None


def normalize_aux_text(aux_body: str) -> str:
    """Canonicalize aux text for caching and dataset conversion."""
    return _AUX_WS_RE.sub(" ", aux_body).strip()


def extract_first_aux_block(completion: str) -> Optional[str]:
    """Return a normalized first aux block suitable as a training target."""
    aux_body = extract_aux_body(completion)
    if aux_body is None:
        return None
    return f"<aux> {normalize_aux_text(aux_body)} </aux>"


def extract_first_tagged_aux_block(completion: str) -> Optional[str]:
    """Return a normalized aux block only when the source contains <aux> tags."""
    if completion is None:
        return None
    match = _AUX_BLOCK_RE.search(str(completion))
    if match is None:
        return None
    return extract_first_aux_block(match.group(0))


# Re-export for backward compatibility
__all__ = [
    "extract_aux_body",
    "normalize_aux_text",
    "extract_first_aux_block",
    "extract_first_tagged_aux_block",
    "try_dsl_to_constructions",
    "try_full_aux_dsl_to_constructions",
    "translate_dsl_to_construction",
]
