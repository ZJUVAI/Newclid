from __future__ import annotations

from typing import Any, Callable


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
        trimmed = [sequence[input_width:] for sequence in sequences[start:end]]
        continuations = decode_batch(trimmed)
        rebuilt_outputs.append(
            [
                _rebuild_prefixed_candidate(request=request, continuation=continuation)
                for continuation in continuations
            ]
        )
    return rebuilt_outputs
