"""Prometheus Instrumentation and Metric Collectors for Workload Simulation.

Exposes production-standard counters, gauges, and histograms:
- Throughput counters (served, failed)
- Dropped request counters with reason labels
- State-labeled worker gauges
- Queue depth and latency histograms
- Real-time CPU and memory utilization gauges
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from interface.schema import TelemetryRecord, WorkerStateEnum


class PrometheusMetricsManager:
    """Manages Prometheus telemetry collectors and registry updates."""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()

        # Throughput counters
        self.requests_total = Counter(
            "workload_requests_total",
            "Total number of requests received by the system",
            ["status", "endpoint"],
            registry=self.registry,
        )

        self.dropped_requests_total = Counter(
            "workload_dropped_requests_total",
            "Total requests dropped due to queue saturation or timeouts",
            ["reason"],
            registry=self.registry,
        )

        # Cluster and Worker Gauges
        self.active_workers = Gauge(
            "workload_active_workers",
            "Number of workers in each lifecycle state",
            ["state"],
            registry=self.registry,
        )

        self.current_capacity_rps = Gauge(
            "workload_current_capacity_rps",
            "Aggregate throughput capacity across ready workers",
            registry=self.registry,
        )

        self.request_rate_current = Gauge(
            "workload_request_rate_current",
            "Instantaneous incoming request arrival rate (RPS)",
            registry=self.registry,
        )

        # Queue Gauges
        self.queue_depth = Gauge(
            "workload_queue_depth",
            "Current number of requests queued in backlog",
            registry=self.registry,
        )

        self.queue_capacity = Gauge(
            "workload_queue_max_capacity",
            "Maximum queue backlog threshold before drops occur",
            registry=self.registry,
        )

        # Resource Utilization Gauges
        self.cpu_utilization = Gauge(
            "workload_cpu_utilization_ratio",
            "Aggregate CPU cores utilization ratio (0.0 to 1.0)",
            registry=self.registry,
        )

        self.memory_used_bytes = Gauge(
            "workload_memory_used_bytes",
            "Memory currently allocated by worker processes",
            registry=self.registry,
        )

        self.memory_total_bytes = Gauge(
            "workload_memory_total_bytes",
            "Total memory budget provisioned for the cluster",
            registry=self.registry,
        )

        # Latency Histograms
        self.request_duration_seconds = Histogram(
            "workload_request_duration_seconds",
            "End-to-end request service latency including queuing time",
            buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry,
        )

        self.queue_wait_seconds = Histogram(
            "workload_queue_wait_duration_seconds",
            "Time spent waiting in queue before processing begins",
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
            registry=self.registry,
        )

    def update_from_record(self, record: TelemetryRecord, endpoint: str = "/api/v1/workload") -> None:
        """Dynamically ingests a TelemetryRecord and updates all registered Prometheus collectors."""
        # 1. Update counters
        served_count = int(round(record.served_rate_rps))
        if served_count > 0:
            self.requests_total.labels(status="200", endpoint=endpoint).inc(served_count)

        if record.error_count > 0:
            status_code = "504" if record.queue.drop_reason.value == "timeout" else "503"
            self.requests_total.labels(status=status_code, endpoint=endpoint).inc(record.error_count)
            self.dropped_requests_total.labels(reason=record.queue.drop_reason.value).inc(record.error_count)

        # 2. Update gauges
        self.request_rate_current.set(record.request_rate_rps)
        self.current_capacity_rps.set(record.workers.current_capacity_rps)
        self.queue_depth.set(record.queue.queue_depth)
        self.queue_capacity.set(record.queue.max_capacity)

        # Worker state gauges
        self.active_workers.labels(state="ready").set(record.workers.ready_workers)
        self.active_workers.labels(state="busy").set(record.workers.busy_workers)
        self.active_workers.labels(state="initializing").set(record.workers.initializing_workers)
        self.active_workers.labels(state="draining").set(record.workers.draining_workers)

        # Resource gauges
        self.cpu_utilization.set(record.resources.cpu_utilization_ratio)
        self.memory_used_bytes.set(record.resources.memory_used_mb * 1024 * 1024)
        self.memory_total_bytes.set(record.resources.memory_total_mb * 1024 * 1024)

        # 3. Update histograms (observe median and tail values)
        p50_sec = record.latency.p50_ms / 1000.0
        p95_sec = record.latency.p95_ms / 1000.0
        p99_sec = record.latency.p99_ms / 1000.0
        self.request_duration_seconds.observe(p50_sec)
        self.request_duration_seconds.observe(p95_sec)
        self.request_duration_seconds.observe(p99_sec)

        self.queue_wait_seconds.observe(record.queue.queue_wait_p95_sec)

    def scrape_latest(self) -> bytes:
        """Generates Prometheus text-format scrape response."""
        return generate_latest(self.registry)
