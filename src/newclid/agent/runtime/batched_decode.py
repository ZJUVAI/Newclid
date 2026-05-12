from __future__ import annotations

from typing import Any, Callable


def strip_trailing_invalid_token_ids(token_ids: list[int]) -> list[int]:
    trimmed = list(token_ids)
    while trimmed and int(trimmed[-1]) < 0:
        trimmed.pop()
    return trimmed


def _rebuild_prefixed_candidate(*, request: dict[str, Any], continuation: str) -> str:
    response_prefix = request.get("response_prefix", "<aux> x00")
    new_point_name = request["new_point_name"]
    return f"{response_prefix} {new_point_name}{continuation}"


def decode_batched_continuations(
    *,
    requests: list[dict[str, Any]],
    model_inputs: dict[str, Any],
    sequences,
    decoding_size: int,
    decode_batch: Callable[[list[Any]], list[str]],
) -> list[list[str]]:
    """Decode only generated continuations from batched left-padded outputs."""
    if not requests:
        return []
    input_width = int(model_inputs["input_ids"].shape[1])
    rebuilt_outputs: list[list[str]] = []
    for index, request in enumerate(requests):
        start = index * decoding_size
        end = start + decoding_size
        trimmed = []
        for sequence in sequences[start:end]:
            continuation_token_ids = sequence[input_width:].tolist()
            trimmed.append(strip_trailing_invalid_token_ids(continuation_token_ids))
        continuations = decode_batch(trimmed)
        rebuilt_outputs.append(
            [
                _rebuild_prefixed_candidate(request=request, continuation=continuation)
                for continuation in continuations
            ]
        )
    return rebuilt_outputs
