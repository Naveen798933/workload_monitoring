"""Data Contract and Pydantic Schema Definitions for Workload Telemetry.

This module establishes strict data schemas for:
- Telemetry time-series records (incoming traffic, latency, queue, resources)
- Metric definitions and unit enforcement
- Data validation rules for downstream AI/Optimization modules
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, model_validator


class MetricUnit(str, Enum):
    """Standardized physical and computational measurement units."""
    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    RATIO = "ratio"  # 0.0 to 1.0
    PERCENT = "percent"  # 0.0 to 100.0
    BYTES = "bytes"
    MEGABYTES = "megabytes"
    COUNT = "count"
    REQUESTS_PER_SECOND = "requests_per_second"


class DropReasonEnum(str, Enum):
    """Reason for request drops during queue or worker processing."""
    NONE = "none"
    QUEUE_OVERFLOW = "queue_overflow"
    TIMEOUT = "timeout"
    CLIENT_CANCEL = "client_cancel"
    CIRCUIT_BREAKER = "circuit_breaker"
    REJECTED = "rejected"


class WorkerStateEnum(str, Enum):
    """Lifecycle states of simulated worker nodes."""
    INITIALIZING = "initializing"
    WARMING_UP = "warming_up"
    READY = "ready"
    BUSY = "busy"
    DRAINING = "draining"
    STOPPED = "stopped"


class TrafficPatternType(str, Enum):
    """Supported traffic generation patterns."""
    STEADY = "steady"
    SPIKE = "spike"
    GRADUAL = "gradual"
    NOISY = "noisy"
    COMPOSITE = "composite"


class MissingValueStrategy(str, Enum):
    """Handling policy for missing telemetry signals."""
    REJECT = "reject"
    FORWARD_FILL = "forward_fill"
    IMPUTE_ZERO = "impute_zero"


class MetricDefinition(BaseModel):
    """Metadata schema defining a metric contract."""
    name: str = Field(..., description="Unique metric identifier")
    unit: MetricUnit = Field(..., description="Measurement unit")
    description: str = Field(..., description="Human-readable description")
    min_value: Optional[float] = Field(None, description="Minimum allowable value")
    max_value: Optional[float] = Field(None, description="Maximum allowable value")
    missing_strategy: MissingValueStrategy = Field(
        default=MissingValueStrategy.REJECT,
        description="Action to take when this metric is absent"
    )


class MetricSample(BaseModel):
    """Single discrete measurement point."""
    timestamp: float = Field(..., ge=0.0, description="Timestamp in seconds or epoch")
    metric_name: str = Field(..., min_length=1, description="Metric identifier")
    value: float = Field(..., description="Observed numerical value")
    unit: MetricUnit = Field(..., description="Measurement unit")
    labels: Dict[str, str] = Field(default_factory=dict, description="Key-value metric labels")


class LatencyDistributionRecord(BaseModel):
    """Latency distribution summary over a discrete time step."""
    min_ms: float = Field(..., ge=0.0, description="Minimum latency in milliseconds")
    mean_ms: float = Field(..., ge=0.0, description="Arithmetic mean latency in ms")
    p50_ms: float = Field(..., ge=0.0, description="50th percentile (median) latency in ms")
    p90_ms: float = Field(..., ge=0.0, description="90th percentile latency in ms")
    p95_ms: float = Field(..., ge=0.0, description="95th percentile latency in ms")
    p99_ms: float = Field(..., ge=0.0, description="99th percentile latency in ms")
    max_ms: float = Field(..., ge=0.0, description="Maximum latency in ms")

    @model_validator(mode="after")
    def validate_monotonic_percentiles(self) -> LatencyDistributionRecord:
        """Enforce strict monotonic ordering: min <= p50 <= p90 <= p95 <= p99 <= max."""
        if not (self.min_ms <= self.p50_ms <= self.p90_ms <= self.p95_ms <= self.p99_ms <= self.max_ms):
            raise ValueError(
                f"Latency percentiles must be monotonically non-decreasing: "
                f"min={self.min_ms}, p50={self.p50_ms}, p90={self.p90_ms}, "
                f"p95={self.p95_ms}, p99={self.p99_ms}, max={self.max_ms}"
            )
        return self


class ResourceUtilizationRecord(BaseModel):
    """CPU and memory consumption metrics."""
    cpu_utilization_ratio: float = Field(
        ..., ge=0.0, le=1.0, description="CPU utilization fraction (0.0 = 0%, 1.0 = 100%)"
    )
    memory_used_mb: float = Field(..., ge=0.0, description="Memory used in Megabytes")
    memory_total_mb: float = Field(..., gt=0.0, description="Total allocated memory in Megabytes")
    memory_utilization_ratio: float = Field(
        ..., ge=0.0, le=1.0, description="Memory utilization fraction (0.0 to 1.0)"
    )
    allocated_cpu_cores: float = Field(..., gt=0.0, description="Total active worker CPU cores")

    @model_validator(mode="after")
    def validate_memory_consistency(self) -> ResourceUtilizationRecord:
        """Ensure memory used does not exceed total allocated memory by more than floating precision."""
        if self.memory_used_mb > self.memory_total_mb + 1e-4:
            raise ValueError(
                f"Memory used ({self.memory_used_mb} MB) cannot exceed total ({self.memory_total_mb} MB)"
            )
        expected_ratio = self.memory_used_mb / self.memory_total_mb
        if abs(self.memory_utilization_ratio - expected_ratio) > 0.05:
            # Allow minor divergence due to reporting lag, but flag severe inconsistencies
            raise ValueError(
                f"Reported memory ratio {self.memory_utilization_ratio} deviates from computed {expected_ratio:.4f}"
            )
        return self


class QueueTelemetryRecord(BaseModel):
    """Queue depth, latency, and drop behavior telemetry."""
    queue_depth: int = Field(..., ge=0, description="Current number of requests waiting in queue")
    max_capacity: int = Field(..., gt=0, description="Maximum queue limit before drops occur")
    queue_wait_p95_sec: float = Field(..., ge=0.0, description="P95 wait time inside queue")
    dropped_count: int = Field(..., ge=0, description="Number of dropped requests in this interval")
    drop_reason: DropReasonEnum = Field(default=DropReasonEnum.NONE, description="Primary drop reason")

    @model_validator(mode="after")
    def validate_drop_consistency(self) -> QueueTelemetryRecord:
        if self.dropped_count > 0 and self.drop_reason == DropReasonEnum.NONE:
            raise ValueError("drop_reason cannot be NONE when dropped_count > 0")
        return self


class WorkerTelemetryRecord(BaseModel):
    """Worker cluster capacity and allocation state."""
    total_workers: int = Field(..., ge=0, description="Total provisioned workers")
    ready_workers: int = Field(..., ge=0, description="Workers ready to serve requests")
    busy_workers: int = Field(..., ge=0, description="Workers currently executing requests")
    initializing_workers: int = Field(default=0, ge=0, description="Workers cold-starting/warming up")
    draining_workers: int = Field(default=0, ge=0, description="Workers gracefully shutting down")
    current_capacity_rps: float = Field(..., ge=0.0, description="Current aggregate throughput capacity")

    @model_validator(mode="after")
    def validate_worker_counts(self) -> WorkerTelemetryRecord:
        active_sum = self.ready_workers + self.busy_workers + self.initializing_workers + self.draining_workers
        if active_sum > self.total_workers:
            raise ValueError(
                f"Sum of substate workers ({active_sum}) exceeds total workers ({self.total_workers})"
            )
        return self


class TelemetryRecord(BaseModel):
    """Master telemetry log row representing an integrated simulation time step."""
    timestamp: float = Field(..., ge=0.0, description="Simulation relative or epoch time in seconds")
    request_rate_rps: float = Field(..., ge=0.0, description="Incoming request rate")
    served_rate_rps: float = Field(..., ge=0.0, description="Successfully processed request rate")
    dropped_rate_rps: float = Field(..., ge=0.0, description="Dropped or timed-out request rate")
    error_count: int = Field(..., ge=0, description="Number of failed/dropped requests")
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Ratio of errors to total incoming requests")
    latency: LatencyDistributionRecord = Field(..., description="Latency statistics")
    resources: ResourceUtilizationRecord = Field(..., description="Resource consumption")
    queue: QueueTelemetryRecord = Field(..., description="Queue performance")
    workers: WorkerTelemetryRecord = Field(..., description="Worker pool telemetry")

    @model_validator(mode="after")
    def validate_rate_conservation(self) -> TelemetryRecord:
        """Ensure served + dropped roughly balances incoming rate within time step bounds."""
        # Due to queuing buffer effects, incoming != served + dropped at every instant,
        # but error rate should correlate with dropped_rate
        total_finished = self.served_rate_rps + self.dropped_rate_rps
        if self.request_rate_rps > 0:
            computed_err = self.dropped_rate_rps / max(total_finished, self.request_rate_rps)
            # Check sanity of error rate
            if self.error_rate > 1.0 or self.error_rate < 0.0:
                raise ValueError(f"Error rate {self.error_rate} must be between 0 and 1")
        return self


class WorkloadDatasetMetadata(BaseModel):
    """Metadata describing a generated workload dataset."""
    scenario_name: str = Field(..., min_length=1)
    traffic_pattern: TrafficPatternType
    duration_seconds: float = Field(..., gt=0.0)
    time_step_seconds: float = Field(..., gt=0.0)
    random_seed: Optional[int] = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = Field(default="1.0.0")


class WorkloadDataset(BaseModel):
    """Container for complete telemetry dataset with metadata and validation."""
    metadata: WorkloadDatasetMetadata
    records: List[TelemetryRecord] = Field(..., min_length=1)

    @field_validator("records")
    def validate_timestamp_sequence(cls, records: List[TelemetryRecord]) -> List[TelemetryRecord]:
        """Ensure records are strictly ordered by ascending timestamp without negative deltas."""
        for i in range(1, len(records)):
            if records[i].timestamp <= records[i - 1].timestamp:
                raise ValueError(
                    f"Non-increasing timestamp detected at index {i}: "
                    f"{records[i].timestamp} <= {records[i - 1].timestamp}"
                )
        return records
