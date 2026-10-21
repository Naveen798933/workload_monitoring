"""CLI Entrypoint for running Workload Simulation, exporting datasets, and plotting.

Usage:
    python simulator/run_simulation.py --config config.yaml --pattern composite --duration 120
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.config import load_config
from simulator.generator import WorkloadGenerator
from simulator.visualizer import WorkloadVisualizer
from model.engine import SimulationEngine
from interface.validator import (
    records_to_dataframe,
    export_dataset_to_csv,
    export_dataset_to_parquet,
)


def run_pipeline(
    config_path: str = "config.yaml",
    pattern: str = "composite",
    duration: float = 120.0,
    seed: int = 42,
    export_format: str = "both",
    output_dir: str = "sample_data",
    generate_plot: bool = True,
) -> None:
    """Executes the full simulation, export, and visualization pipeline."""
    overrides = {
        "simulation": {
            "duration_seconds": duration,
            "random_seed": seed,
            "export_format": export_format,
            "output_dir": output_dir,
        },
        "traffic_generator": {
            "active_pattern": pattern,
        },
    }

    config = load_config(config_path=config_path, overrides=overrides)
    print(f"[*] Loaded configuration from: {config_path}")
    print(f"[*] Running pattern='{pattern}', duration={duration}s, seed={seed}")

    # 1. Generate traffic
    generator = WorkloadGenerator(config=config, random_seed=seed)
    traffic_df = generator.generate(pattern_type=pattern)
    print(f"[+] Traffic timeline generated: {len(traffic_df)} time steps")

    # 2. Simulate resource performance and queues
    engine = SimulationEngine(config=config, random_seed=seed)
    telemetry_records = engine.run_simulation(traffic_df)
    telemetry_df = records_to_dataframe(telemetry_records)
    print(f"[+] Performance model completed: {len(telemetry_df)} telemetry rows recorded")

    # 3. Export datasets
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / config["simulation"].get("output_csv_filename", "simulated_workload_telemetry.csv")
    parquet_path = out_dir / config["simulation"].get("output_parquet_filename", "simulated_workload_telemetry.parquet")

    fmt = export_format.lower()
    if fmt in ("csv", "both"):
        saved_csv = export_dataset_to_csv(telemetry_df, csv_path)
        print(f"[+] Exported CSV telemetry to: {saved_csv}")

    if fmt in ("parquet", "both"):
        saved_pq = export_dataset_to_parquet(telemetry_df, parquet_path)
        print(f"[+] Exported Parquet telemetry to: {saved_pq}")

    # 4. Generate dynamic Matplotlib visualization
    if generate_plot:
        plot_dest = out_dir / "workload_timeline.png"
        visualizer = WorkloadVisualizer(config=config)
        saved_img = visualizer.plot_timeline(
            df=telemetry_df,
            output_path=plot_dest,
            title=f"Workload Telemetry Timeline [{pattern.upper()} pattern, seed={seed}]",
        )
        print(f"[+] Visualization saved to: {saved_img}")

    print("[*] Workload Simulation Pipeline executed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Workload Simulation CLI")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--pattern", type=str, default="composite", choices=["steady", "spike", "gradual", "noisy", "composite"])
    parser.add_argument("--duration", type=float, default=120.0, help="Simulation duration in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--export-format", type=str, default="both", choices=["csv", "parquet", "both"])
    parser.add_argument("--output-dir", type=str, default="sample_data", help="Output directory for datasets and plots")
    parser.add_argument("--no-plot", action="store_true", help="Disable Matplotlib visualization generation")

    args = parser.parse_args()
    run_pipeline(
        config_path=args.config,
        pattern=args.pattern,
        duration=args.duration,
        seed=args.seed,
        export_format=args.export_format,
        output_dir=args.output_dir,
        generate_plot=not args.no_plot,
    )
