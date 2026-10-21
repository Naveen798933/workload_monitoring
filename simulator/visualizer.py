"""Dynamic Telemetry and Traffic Timeline Visualizer using Matplotlib.

Zero Hardcoding: Figure dimensions, DPI, line styles, color palettes,
and output destinations are all driven dynamically by configuration or method arguments.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Union
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend safe for headless servers / CI
import matplotlib.pyplot as plt
import pandas as pd


class WorkloadVisualizer:
    """Renders comprehensive multi-panel telemetry timelines from simulated datasets."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.vis_cfg: Dict[str, Any] = self.config.get("visualization", {})
        self.colors: Dict[str, str] = self.vis_cfg.get("colors", {
            "request_rate": "#2563EB",
            "capacity_rate": "#10B981",
            "latency_p50": "#F59E0B",
            "latency_p95": "#F97316",
            "latency_p99": "#EF4444",
            "cpu_util": "#8B5CF6",
            "memory_util": "#06B6D4",
            "queue_depth": "#EC4899",
            "dropped": "#DC2626",
        })

    def plot_timeline(
        self,
        df: pd.DataFrame,
        output_path: Optional[Union[str, Path]] = None,
        title: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Plots a dynamic 4-panel telemetry dashboard from a telemetry DataFrame.

        Panels:
        1. Incoming Traffic Rate vs Aggregate System Capacity vs Dropped Rate
        2. Latency Percentiles (p50, p95, p99) over time
        3. Resource Utilization (CPU cores ratio & Memory utilization ratio)
        4. Queue Backpressure (Queue depth vs Max capacity)
        """
        params = custom_params or self.vis_cfg
        width = float(params.get("figure_width_inches", 14.0))
        height = float(params.get("figure_height_inches", 10.0))
        dpi = int(params.get("dpi", 300))
        dest_path = output_path or params.get("save_path", "sample_data/workload_timeline.png")

        fig, axes = plt.subplots(4, 1, figsize=(width, height), sharex=True, dpi=dpi)
        fig.suptitle(title or "Distributed Workload Simulation & Telemetry Timeline", fontsize=16, fontweight="bold", y=0.98)

        t = df["timestamp"]

        # Panel 1: Throughput & Capacity
        ax1 = axes[0]
        if "request_rate_rps" in df:
            ax1.plot(t, df["request_rate_rps"], label="Incoming Request Rate (RPS)", color=self.colors.get("request_rate", "#2563EB"), lw=2.0)
        if "workers_capacity_rps" in df:
            ax1.plot(t, df["workers_capacity_rps"], label="Cluster Capacity (RPS)", color=self.colors.get("capacity_rate", "#10B981"), lw=2.0, linestyle="--")
        if "dropped_rate_rps" in df and df["dropped_rate_rps"].sum() > 0:
            ax1.plot(t, df["dropped_rate_rps"], label="Dropped Rate (RPS)", color=self.colors.get("dropped", "#DC2626"), lw=1.5, linestyle=":")
        ax1.set_ylabel("Throughput (RPS)", fontweight="semibold")
        ax1.legend(loc="upper right", framealpha=0.9)
        ax1.grid(True, linestyle="--", alpha=0.5)

        # Panel 2: Latency Percentiles
        ax2 = axes[1]
        if "latency_p50_ms" in df:
            ax2.plot(t, df["latency_p50_ms"], label="p50 (Median)", color=self.colors.get("latency_p50", "#F59E0B"), lw=1.8)
        if "latency_p95_ms" in df:
            ax2.plot(t, df["latency_p95_ms"], label="p95 Tail", color=self.colors.get("latency_p95", "#F97316"), lw=2.0)
        if "latency_p99_ms" in df:
            ax2.plot(t, df["latency_p99_ms"], label="p99 Peak", color=self.colors.get("latency_p99", "#EF4444"), lw=2.2)
            if "latency_p50_ms" in df:
                ax2.fill_between(t, df["latency_p50_ms"], df["latency_p99_ms"], color=self.colors.get("latency_p99", "#EF4444"), alpha=0.12)
        ax2.set_ylabel("Latency (ms)", fontweight="semibold")
        ax2.legend(loc="upper right", framealpha=0.9)
        ax2.grid(True, linestyle="--", alpha=0.5)

        # Panel 3: Resource Utilization
        ax3 = axes[2]
        if "cpu_utilization_ratio" in df:
            ax3.plot(t, df["cpu_utilization_ratio"] * 100.0, label="CPU Util (%)", color=self.colors.get("cpu_util", "#8B5CF6"), lw=2.0)
        if "memory_utilization_ratio" in df:
            ax3.plot(t, df["memory_utilization_ratio"] * 100.0, label="Memory Util (%)", color=self.colors.get("memory_util", "#06B6D4"), lw=2.0, linestyle="-.")
        ax3.set_ylabel("Utilization (%)", fontweight="semibold")
        ax3.set_ylim(-5, 105)
        ax3.axhline(80.0, color="#EF4444", linestyle=":", alpha=0.7, label="Target Scaler Threshold (80%)")
        ax3.legend(loc="upper right", framealpha=0.9)
        ax3.grid(True, linestyle="--", alpha=0.5)

        # Panel 4: Queue Backpressure
        ax4 = axes[3]
        if "queue_depth" in df:
            ax4.plot(t, df["queue_depth"], label="Queue Depth (Requests)", color=self.colors.get("queue_depth", "#EC4899"), lw=2.0)
        if "queue_max_capacity" in df:
            ax4.axhline(df["queue_max_capacity"].iloc[0], color="#DC2626", linestyle="--", alpha=0.8, label=f"Max Queue Cap ({df['queue_max_capacity'].iloc[0]})")
        ax4.set_xlabel("Elapsed Time (Seconds)", fontweight="semibold")
        ax4.set_ylabel("Backlog Depth", fontweight="semibold")
        ax4.legend(loc="upper right", framealpha=0.9)
        ax4.grid(True, linestyle="--", alpha=0.5)

        plt.tight_layout(rect=[0, 0, 1, 0.96])

        # Ensure destination directory exists
        dest_file = Path(dest_path)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(dest_file, dpi=dpi, bbox_inches="tight")
        plt.close(fig)

        return str(dest_file.resolve())
