"""Centralized dynamic configuration loader for Workload Simulation & Monitoring.

Zero hardcoding mandate: All parameters are sourced from YAML/JSON files,
environment variable overrides, or dynamic parameter injection.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merges dictionary overrides into a base dictionary."""
    result = base.copy()
    for key, value in overrides.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    config_path: Optional[str | Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Loads configuration with environment variable overrides and dynamic parameter injection.

    Hierarchy:
    1. Base YAML configuration file (path passed or WORKLOAD_CONFIG_PATH env var)
    2. Specific environment variables (e.g., SIM_DURATION_SEC, SIM_SEED, SIM_EXPORT_FORMAT)
    3. Explicit programmatic overrides dictionary
    """
    path = config_path or os.getenv("WORKLOAD_CONFIG_PATH") or DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Environment variable overrides
    if "SIM_DURATION_SEC" in os.environ:
        config.setdefault("simulation", {})["duration_seconds"] = float(os.environ["SIM_DURATION_SEC"])
    if "SIM_SEED" in os.environ:
        config.setdefault("simulation", {})["random_seed"] = int(os.environ["SIM_SEED"])
    if "SIM_EXPORT_FORMAT" in os.environ:
        config.setdefault("simulation", {})["export_format"] = os.environ["SIM_EXPORT_FORMAT"]
    if "TRAFFIC_PATTERN" in os.environ:
        config.setdefault("traffic_generator", {})["active_pattern"] = os.environ["TRAFFIC_PATTERN"]
    if "METRICS_PORT" in os.environ:
        config.setdefault("monitoring", {}).setdefault("exporter", {})["port"] = int(os.environ["METRICS_PORT"])

    # Programmatic overrides
    if overrides:
        config = deep_merge(config, overrides)

    return config
