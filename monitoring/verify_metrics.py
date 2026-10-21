"""Verification script: Validates that Prometheus exposed metrics match simulator raw outputs.

Ensures telemetry integrity between internal state and external observability scrape responses.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure repository root is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.config import load_config
from simulator.generator import WorkloadGenerator
from model.engine import SimulationEngine
from monitoring.metrics import PrometheusMetricsManager


def parse_prometheus_text(scrape_text: str) -> Dict[str, float]:
    """Parses standard Prometheus text exposition format into metric-name -> value dictionary."""
    metrics: Dict[str, float] = {}
    for line in scrape_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Match lines like: metric_name{label="val"} 123.45 or metric_name 123.45
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})?)\s+([+-]?(?:[0-9]*[.])?[0-9]+(?:[eE][+-]?[0-9]+)?)$", line)
        if match:
            metric_identifier, val_str = match.groups()
            metrics[metric_identifier] = float(val_str)
    return metrics


def verify_telemetry_fidelity() -> bool:
    """Runs a controlled simulation test step and validates exposed Prometheus metrics against raw state."""
    config = load_config()
    engine = SimulationEngine(config=config, random_seed=42)
    manager = PrometheusMetricsManager()

    print("[Verification] Running controlled simulation step...")
    # Step with 75 RPS
    record = engine.step(current_time=1.0, incoming_rate_rps=75.0)
    manager.update_from_record(record)

    scrape_raw = manager.scrape_latest().decode("utf-8")
    parsed = parse_prometheus_text(scrape_raw)

    print(f"[Verification] Scraped {len(parsed)} metrics from Prometheus registry.")

    # 1. Verify queue depth gauge
    q_depth = parsed.get("workload_queue_depth")
    assert q_depth is not None, "Missing metric: workload_queue_depth"
    assert q_depth == float(record.queue.queue_depth), (
        f"Queue depth mismatch: Prometheus={q_depth}, Simulator={record.queue.queue_depth}"
    )

    # 2. Verify worker capacity gauge
    cap_rps = parsed.get("workload_current_capacity_rps")
    assert cap_rps is not None, "Missing metric: workload_current_capacity_rps"
    assert cap_rps == float(record.workers.current_capacity_rps), (
        f"Capacity mismatch: Prometheus={cap_rps}, Simulator={record.workers.current_capacity_rps}"
    )

    # 3. Verify CPU utilization gauge
    cpu_util = parsed.get("workload_cpu_utilization_ratio")
    assert cpu_util is not None, "Missing metric: workload_cpu_utilization_ratio"
    assert abs(cpu_util - record.resources.cpu_utilization_ratio) < 1e-3, (
        f"CPU util mismatch: Prometheus={cpu_util}, Simulator={record.resources.cpu_utilization_ratio}"
    )

    # 4. Verify request arrival rate gauge
    rate_curr = parsed.get("workload_request_rate_current")
    assert rate_curr is not None, "Missing metric: workload_request_rate_current"
    assert rate_curr == float(record.request_rate_rps), (
        f"Request rate mismatch: Prometheus={rate_curr}, Simulator={record.request_rate_rps}"
    )

    # 5. Verify worker states
    ready_workers = parsed.get('workload_active_workers{state="ready"}')
    assert ready_workers is not None, "Missing metric: workload_active_workers{state=\"ready\"}"
    assert ready_workers == float(record.workers.ready_workers), (
        f"Ready worker mismatch: Prometheus={ready_workers}, Simulator={record.workers.ready_workers}"
    )

    print("[Verification] PASSED: All Prometheus scraped metrics exactly match simulator raw output!")
    return True


if __name__ == "__main__":
    success = verify_telemetry_fidelity()
    if not success:
        sys.exit(1)
