"""Compatibility wrapper for optional tqdm progress bars."""

from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")

try:
    from tqdm import tqdm as _tqdm
except ModuleNotFoundError:

    def tqdm(iterable: Iterable[T], *args, **kwargs) -> Iterable[T]:
        return iterable
else:
    tqdm = _tqdm
