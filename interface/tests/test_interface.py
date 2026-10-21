"""Unit tests for Interface contracts and Pydantic schema validation."""

import pytest
from pydantic import ValidationError
from interface.schema import (
    DropReasonEnum,
    LatencyDistributionRecord,
    QueueTelemetryRecord,
    ResourceUtilizationRecord,
    TelemetryRecord,
    WorkerStateEnum,
    WorkerTelemetryRecord,
)
from interface.validator import (
    flatten_telemetry_record,
    unflatten_row_to_telemetry_record,
    records_to_dataframe,
    dataframe_to_records,
)


def create_valid_telemetry_record() -> TelemetryRecord:
    return TelemetryRecord(
        timestamp=10.0,
        request_rate_rps=50.0,
        served_rate_rps=50.0,
        dropped_rate_rps=0.0,
        error_count=0,
        error_rate=0.0,
        latency=LatencyDistributionRecord(
            min_ms=10.0,
            mean_ms=25.0,
            p50_ms=22.0,
            p90_ms=35.0,
            p95_ms=45.0,
            p99_ms=60.0,
            max_ms=90.0,
        ),
        resources=ResourceUtilizationRecord(
            cpu_utilization_ratio=0.55,
            memory_used_mb=1024.0,
            memory_total_mb=4096.0,
            memory_utilization_ratio=0.25,
            allocated_cpu_cores=4.0,
        ),
        queue=QueueTelemetryRecord(
            queue_depth=5,
            max_capacity=500,
            queue_wait_p95_sec=0.012,
            dropped_count=0,
            drop_reason=DropReasonEnum.NONE,
        ),
        workers=WorkerTelemetryRecord(
            total_workers=4,
            ready_workers=3,
            busy_workers=1,
            initializing_workers=0,
            draining_workers=0,
            current_capacity_rps=100.0,
        ),
    )


def test_valid_telemetry_record_instantiation():
    record = create_valid_telemetry_record()
    assert record.timestamp == 10.0
    assert record.request_rate_rps == 50.0


def test_reject_non_monotonic_latency():
    """Fail if p95 is lower than p50."""
    with pytest.raises(ValidationError):
        LatencyDistributionRecord(
            min_ms=10.0,
            mean_ms=25.0,
            p50_ms=50.0,  # Higher than p95
            p90_ms=60.0,
            p95_ms=30.0,  # Inversion!
            p99_ms=80.0,
            max_ms=100.0,
        )


def test_reject_negative_latency():
    """Fail on negative latency numbers."""
    with pytest.raises(ValidationError):
        LatencyDistributionRecord(
            min_ms=-5.0,
            mean_ms=20.0,
            p50_ms=20.0,
            p90_ms=30.0,
            p95_ms=40.0,
            p99_ms=50.0,
            max_ms=60.0,
        )


def test_reject_excessive_cpu_utilization():
    """Fail if CPU utilization ratio > 1.0."""
    with pytest.raises(ValidationError):
        ResourceUtilizationRecord(
            cpu_utilization_ratio=1.45,  # > 1.0 invalid
            memory_used_mb=500.0,
            memory_total_mb=1024.0,
            memory_utilization_ratio=0.488,
            allocated_cpu_cores=2.0,
        )


def test_reject_memory_exceeding_total():
    """Fail if memory used exceeds memory total."""
    with pytest.raises(ValidationError):
        ResourceUtilizationRecord(
            cpu_utilization_ratio=0.5,
            memory_used_mb=5000.0,  # Exceeds total!
            memory_total_mb=2048.0,
            memory_utilization_ratio=0.5,
            allocated_cpu_cores=2.0,
        )


def test_reject_drop_count_without_reason():
    """Fail if dropped_count > 0 but drop_reason is NONE."""
    with pytest.raises(ValidationError):
        QueueTelemetryRecord(
            queue_depth=10,
            max_capacity=100,
            queue_wait_p95_sec=0.5,
            dropped_count=5,
            drop_reason=DropReasonEnum.NONE,  # Inconsistent
        )


def test_dataframe_roundtrip_fidelity():
    """Verify serialization to DataFrame and unflattening preserves all fields."""
    rec = create_valid_telemetry_record()
    df = records_to_dataframe([rec])
    restored_list = dataframe_to_records(df)

    assert len(restored_list) == 1
    restored = restored_list[0]
    assert restored.timestamp == rec.timestamp
    assert restored.request_rate_rps == rec.request_rate_rps
    assert restored.latency.p95_ms == rec.latency.p95_ms
    assert restored.resources.cpu_utilization_ratio == rec.resources.cpu_utilization_ratio
    assert restored.queue.queue_depth == rec.queue.queue_depth
    assert restored.workers.current_capacity_rps == rec.workers.current_capacity_rps
