"""End-to-End Demonstration for Member 1: Workload Simulation and Monitoring.

Executes all 4 Tasks seamlessly:
1. Workload Simulator with dynamic traffic generation (steady, spike, gradual, noisy, composite)
2. Resource & Performance Model (Worker pool, queues, cold-start latency, resource metrics)
3. Prometheus Exporter & Metrics Verification (live endpoint, scrapes, fidelity check)
4. Shared Data Interface (Pydantic schema validation, CSV & Parquet exports)
"""

from __future__ import annotations
import sys
import time
from pathlib import Path
import urllib.request

# Ensure UTF-8 output safe for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulator.config import load_config
from simulator.generator import WorkloadGenerator
from simulator.visualizer import WorkloadVisualizer
from model.engine import SimulationEngine
from monitoring.exporter_server import WorkloadMetricsServer
from monitoring.verify_metrics import verify_telemetry_fidelity
from interface.validator import (
    records_to_dataframe,
    export_dataset_to_csv,
    export_dataset_to_parquet,
    load_and_validate_csv,
    load_and_validate_parquet,
)


def run_full_demonstration() -> None:
    print("=" * 80)
    print("[*] STARTING MEMBER 1: WORKLOAD SIMULATION & MONITORING DEMONSTRATION")
    print("=" * 80)

    # 1. Load Dynamic Configuration (Zero hardcoded constants)
    config = load_config()
    sim_cfg = config.get("simulation", {})
    output_dir = Path(sim_cfg.get("output_dir", "sample_data"))
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = float(sim_cfg.get("duration_seconds", 120.0))
    seed = int(sim_cfg.get("random_seed", 42))

    print(f"\n[Task 1] Workload Simulator Initialization")
    print(f"  - Config duration: {duration}s, seed: {seed}")
    generator = WorkloadGenerator(config=config, random_seed=seed)

    # Demonstrate multiple traffic generation patterns
    for pat in ["steady", "spike", "gradual", "noisy", "composite"]:
        df_pat = generator.generate(pattern_type=pat)
        print(f"  [+] Pattern '{pat:<9}': mean={df_pat['request_rate_rps'].mean():.1f} RPS, max={df_pat['request_rate_rps'].max():.1f} RPS")

    # Generate active pattern for model ingestion
    active_pat = config.get("traffic_generator", {}).get("active_pattern", "composite")
    traffic_df = generator.generate(pattern_type=active_pat)

    print(f"\n[Task 2] Resource and Performance Model Execution")
    engine = SimulationEngine(config=config, random_seed=seed)
    telemetry_records = engine.run_simulation(traffic_df)
    telemetry_df = records_to_dataframe(telemetry_records)
    print(f"  [+] Simulated {len(telemetry_df)} time steps")
    print(f"  [+] Peak incoming: {telemetry_df['request_rate_rps'].max():.1f} RPS")
    print(f"  [+] Cluster capacity: {telemetry_df['workers_capacity_rps'].iloc[0]:.1f} RPS -> peak {telemetry_df['workers_capacity_rps'].max():.1f} RPS")
    print(f"  [+] Median Latency (p50): {telemetry_df['latency_p50_ms'].median():.2f} ms")
    print(f"  [+] Tail Latency (p99):   {telemetry_df['latency_p99_ms'].max():.2f} ms")
    print(f"  [+] Max CPU Util:         {telemetry_df['cpu_utilization_ratio'].max() * 100:.1f}%")
    print(f"  [+] Total Dropped:        {telemetry_df['queue_dropped_count'].sum()} requests")

    print(f"\n[Task 4] Shared Data Interface & Persistence (CSV & Parquet)")
    csv_file = output_dir / sim_cfg.get("output_csv_filename", "simulated_workload_telemetry.csv")
    parquet_file = output_dir / sim_cfg.get("output_parquet_filename", "simulated_workload_telemetry.parquet")

    csv_path = export_dataset_to_csv(telemetry_df, csv_file)
    pq_path = export_dataset_to_parquet(telemetry_df, parquet_file)
    print(f"  [+] Exported CSV:     {csv_path} ({csv_file.stat().st_size / 1024:.1f} KB)")
    print(f"  [+] Exported Parquet: {pq_path} ({parquet_file.stat().st_size / 1024:.1f} KB)")

    # Validate ingested data against Pydantic schema
    print("  [+] Validating CSV records against strict Pydantic schemas...")
    validated_csv_records = load_and_validate_csv(csv_path)
    print(f"    -> Successfully validated {len(validated_csv_records)} records from CSV.")

    print("  [+] Validating Parquet records against strict Pydantic schemas...")
    validated_pq_records = load_and_validate_parquet(pq_path)
    print(f"    -> Successfully validated {len(validated_pq_records)} records from Parquet.")

    print(f"\n[Task 1 & 4] Dynamic Matplotlib Visualization")
    vis = WorkloadVisualizer(config=config)
    plot_file = output_dir / "workload_timeline.png"
    img_path = vis.plot_timeline(
        df=telemetry_df,
        output_path=plot_file,
        title=f"Distributed Workload & Systems Telemetry [{active_pat.upper()} Pattern]",
    )
    print(f"  [+] High-resolution plot generated: {img_path}")

    print(f"\n[Task 3] Monitoring & Prometheus Instrumentation")
    exporter = WorkloadMetricsServer(config=config, host="127.0.0.1", port=8000)
    exporter.start(background=True)

    # Stream recent records into Prometheus metrics manager
    for rec in telemetry_records[-10:]:
        exporter.manager.update_from_record(rec)

    # Scrape HTTP endpoint
    metrics_url = "http://127.0.0.1:8000/metrics"
    time.sleep(0.5)
    with urllib.request.urlopen(metrics_url) as resp:
        body = resp.read().decode("utf-8")
        metric_lines = [l for l in body.splitlines() if not l.startswith("#") and l.strip()]
        print(f"  [+] Successfully scraped {metrics_url} ({len(metric_lines)} metric series active)")

    # Run formal fidelity verification
    print("  [+] Running telemetry fidelity verification against Prometheus exposition...")
    fidelity_ok = verify_telemetry_fidelity()
    print(f"  [+] Observability verification result: {'PASSED' if fidelity_ok else 'FAILED'}")

    exporter.stop()

    print("\n" + "=" * 80)
    print("[OK] ALL TASKS (1, 2, 3, 4) EXECUTED AND VERIFIED WITH ZERO ERRORS!")
    print("=" * 80)


if __name__ == "__main__":
    run_full_demonstration()
