import newclid
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict


def default_configs_path() -> Path:
    return Path(newclid.__file__).parent.joinpath("default_configs")


def default_defs_path() -> Path:
    return default_configs_path().joinpath("defs.txt")


def default_rules_path() -> Path:
    return default_configs_path().joinpath("rules.txt")


def default_solver_config_path() -> Path:
    return default_configs_path().joinpath("solver_config.json")


def load_solver_config(config_path: Path = None, **overrides) -> Dict[str, bool]:
    """
    Load solver configuration from JSON file with optional overrides.

    Args:
        config_path: Path to config file. If None, uses default.
        **overrides: Temporary parameter overrides (e.g., using_log=True)

    Returns:
        Dict with all bool configuration values
    """
    if config_path is None:
        config_path = default_solver_config_path()

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Apply overrides
    config.update(overrides)

    return config


@lru_cache(maxsize=None)
def load_default_ddar_runtime_config(
    using_log: bool = True,
    using_exp: bool = True,
) -> Dict[str, bool]:
    """Return the default DDAR config with explicit runtime overrides."""
    return load_solver_config(using_log=using_log, using_exp=using_exp)
