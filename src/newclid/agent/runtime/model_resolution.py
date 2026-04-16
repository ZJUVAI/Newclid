from __future__ import annotations

import logging
from pathlib import Path
import sys
import types


logger = logging.getLogger(__name__)

try:
    import modelscope as _modelscope
except ModuleNotFoundError:
    _modelscope = types.ModuleType("modelscope")

    def _missing_snapshot_download(*args, **kwargs):
        raise ImportError(
            "modelscope is required to load remote model ids. "
            "Install modelscope or pass a local model path."
        )

    _modelscope.snapshot_download = _missing_snapshot_download
    sys.modules["modelscope"] = _modelscope


def resolve_model_path(path: str) -> str:
    candidate = Path(path).expanduser()
    if candidate.exists():
        resolved = str(candidate.resolve())
        logger.info("Loading experiment model from local path: %s", resolved)
        return resolved
    if candidate.is_absolute() or path.startswith(".") or path.startswith("~"):
        raise FileNotFoundError(f"Model path does not exist: {candidate}")

    logger.info("Downloading/loading experiment model via ModelScope: %s", path)
    resolved = _modelscope.snapshot_download(path)
    logger.info("Resolved experiment model id %s to local path: %s", path, resolved)
    return resolved
