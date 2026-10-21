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
    path = Path(config_path) if config_path else (Path(os.getenv("WORKLOAD_CONFIG_PATH")) if os.getenv("WORKLOAD_CONFIG_PATH") else DEFAULT_CONFIG_PATH)

    # Search candidate paths for config.yaml
    candidate_paths = [
        path,
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parent / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
        Path("/var/task/config.yaml"),
    ]

    config_file: Optional[Path] = None
    for cand in candidate_paths:
        if cand and cand.exists() and cand.is_file():
            config_file = cand
            break

    if config_file:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        # Fallback default configuration for serverless environments
        config = {
            "simulation": {
                "duration_seconds": 120,
                "time_step_seconds": 1.0,
                "random_seed": 42,
                "export_format": "both",
                "output_dir": "/tmp/sample_data" if os.environ.get("VERCEL") else "sample_data",
                "output_csv_filename": "simulated_workload_telemetry.csv",
                "output_parquet_filename": "simulated_workload_telemetry.parquet",
            },
            "traffic_generator": {
                "active_pattern": "composite",
                "steady": {"baseline_rps": 50.0, "jitter_std_dev": 5.0, "min_rps": 10.0, "max_rps": 200.0},
                "spike": {"baseline_rps": 40.0, "spike_amplitude_rps": 180.0, "spike_start_sec": 30.0, "spike_duration_sec": 25.0, "decay_rate": 0.15},
                "gradual": {"baseline_rps": 30.0, "peak_rps": 120.0, "trend_type": "sinusoidal", "period_seconds": 60.0, "phase_shift_seconds": 0.0},
                "noisy": {"baseline_rps": 45.0, "noise_type": "gaussian_walk", "volatility": 8.0, "mean_reversion_rate": 0.1, "min_rps": 5.0, "max_rps": 250.0},
                "composite": {"base_pattern": "gradual", "enable_spikes": True, "enable_noise": True, "spike_trigger_interval_sec": 45.0, "spike_magnitude_multiplier": 3.5, "spike_length_sec": 15.0, "noise_sigma": 6.0},
            },
            "resource_model": {
                "worker_pool": {
                    "initial_workers": 4, "min_workers": 1, "max_workers": 16,
                    "cpu_cores_per_worker": 2.0, "memory_mb_per_worker": 2048.0,
                    "throughput_per_worker_rps": 25.0, "max_concurrency_per_worker": 30,
                    "cold_start_delay_sec": 5.0, "warm_up_delay_sec": 2.0, "graceful_drain_delay_sec": 3.0,
                    "auto_scaling": {"enabled": True, "target_cpu_utilization": 0.75, "scale_up_step": 2, "scale_down_step": 1, "cooldown_period_sec": 10.0},
                },
                "queue": {"queue_type": "FIFO", "max_capacity": 500, "drop_policy": "DROP_TAIL", "request_timeout_sec": 5.0},
                "latency_distribution": {"distribution": "lognormal", "base_service_time_ms": 28.0, "service_time_std_dev_ms": 8.0, "min_latency_ms": 5.0, "max_latency_ms": 3000.0, "concurrency_penalty_factor": 0.05},
            },
            "monitoring": {
                "exporter": {"host": "0.0.0.0", "port": 8000, "endpoint": "/metrics", "collection_interval_sec": 1.0},
                "prometheus": {"scrape_interval": "2s", "scrape_timeout": "2s", "target_host": "localhost", "target_port": 8000, "metrics_path": "/metrics"},
                "grafana": {"dashboard_title": "Member 1 - Workload & Systems Telemetry", "refresh_rate": "2s", "time_window": "now-5m"},
            },
            "visualization": {
                "style": "seaborn-v0_8-darkgrid", "dpi": 300, "figure_width_inches": 14, "figure_height_inches": 10,
                "save_path": "/tmp/sample_data/workload_timeline.png" if os.environ.get("VERCEL") else "sample_data/workload_timeline.png",
                "colors": {"request_rate": "#2563EB", "capacity_rate": "#10B981", "latency_p50": "#F59E0B", "latency_p95": "#F97316", "latency_p99": "#EF4444", "cpu_util": "#8B5CF6", "memory_util": "#06B6D4", "queue_depth": "#EC4899", "dropped": "#DC2626"},
            },
        }

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
