"""Ingestion, serialization, and validation pipeline for Workload Telemetry.

Provides bi-directional conversion between tabular datasets (CSV/Parquet),
Pandas DataFrames, and strict Pydantic TelemetryRecord schemas.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Union
import pandas as pd
from pydantic import ValidationError

from interface.schema import (
    TelemetryRecord,
    WorkloadDataset,
    WorkloadDatasetMetadata,
    LatencyDistributionRecord,
    ResourceUtilizationRecord,
    QueueTelemetryRecord,
    WorkerTelemetryRecord,
    DropReasonEnum,
    TrafficPatternType,
)


def flatten_telemetry_record(record: TelemetryRecord) -> Dict[str, Any]:
    """Flattens a hierarchical TelemetryRecord into a flat dictionary suitable for CSV/Parquet."""
    return {
        "timestamp": record.timestamp,
        "request_rate_rps": record.request_rate_rps,
        "served_rate_rps": record.served_rate_rps,
        "dropped_rate_rps": record.dropped_rate_rps,
        "error_count": record.error_count,
        "error_rate": record.error_rate,
        # Latency metrics
        "latency_min_ms": record.latency.min_ms,
        "latency_mean_ms": record.latency.mean_ms,
        "latency_p50_ms": record.latency.p50_ms,
        "latency_p90_ms": record.latency.p90_ms,
        "latency_p95_ms": record.latency.p95_ms,
        "latency_p99_ms": record.latency.p99_ms,
        "latency_max_ms": record.latency.max_ms,
        # Resources metrics
        "cpu_utilization_ratio": record.resources.cpu_utilization_ratio,
        "memory_used_mb": record.resources.memory_used_mb,
        "memory_total_mb": record.resources.memory_total_mb,
        "memory_utilization_ratio": record.resources.memory_utilization_ratio,
        "allocated_cpu_cores": record.resources.allocated_cpu_cores,
        # Queue metrics
        "queue_depth": record.queue.queue_depth,
        "queue_max_capacity": record.queue.max_capacity,
        "queue_wait_p95_sec": record.queue.queue_wait_p95_sec,
        "queue_dropped_count": record.queue.dropped_count,
        "queue_drop_reason": record.queue.drop_reason.value,
        # Worker metrics
        "workers_total": record.workers.total_workers,
        "workers_ready": record.workers.ready_workers,
        "workers_busy": record.workers.busy_workers,
        "workers_initializing": record.workers.initializing_workers,
        "workers_draining": record.workers.draining_workers,
        "workers_capacity_rps": record.workers.current_capacity_rps,
    }


def unflatten_row_to_telemetry_record(row: Dict[str, Any]) -> TelemetryRecord:
    """Converts a flat dictionary or DataFrame row into a validated TelemetryRecord."""
    drop_reason_str = str(row.get("queue_drop_reason", "none")).lower()
    try:
        drop_reason = DropReasonEnum(drop_reason_str)
    except ValueError:
        drop_reason = DropReasonEnum.NONE

    return TelemetryRecord(
        timestamp=float(row["timestamp"]),
        request_rate_rps=float(row["request_rate_rps"]),
        served_rate_rps=float(row["served_rate_rps"]),
        dropped_rate_rps=float(row["dropped_rate_rps"]),
        error_count=int(row["error_count"]),
        error_rate=float(row["error_rate"]),
        latency=LatencyDistributionRecord(
            min_ms=float(row["latency_min_ms"]),
            mean_ms=float(row["latency_mean_ms"]),
            p50_ms=float(row["latency_p50_ms"]),
            p90_ms=float(row["latency_p90_ms"]),
            p95_ms=float(row["latency_p95_ms"]),
            p99_ms=float(row["latency_p99_ms"]),
            max_ms=float(row["latency_max_ms"]),
        ),
        resources=ResourceUtilizationRecord(
            cpu_utilization_ratio=float(row["cpu_utilization_ratio"]),
            memory_used_mb=float(row["memory_used_mb"]),
            memory_total_mb=float(row["memory_total_mb"]),
            memory_utilization_ratio=float(row["memory_utilization_ratio"]),
            allocated_cpu_cores=float(row["allocated_cpu_cores"]),
        ),
        queue=QueueTelemetryRecord(
            queue_depth=int(row["queue_depth"]),
            max_capacity=int(row["queue_max_capacity"]),
            queue_wait_p95_sec=float(row["queue_wait_p95_sec"]),
            dropped_count=int(row["queue_dropped_count"]),
            drop_reason=drop_reason,
        ),
        workers=WorkerTelemetryRecord(
            total_workers=int(row["workers_total"]),
            ready_workers=int(row["workers_ready"]),
            busy_workers=int(row["workers_busy"]),
            initializing_workers=int(row.get("workers_initializing", 0)),
            draining_workers=int(row.get("workers_draining", 0)),
            current_capacity_rps=float(row["workers_capacity_rps"]),
        ),
    )


def records_to_dataframe(records: List[TelemetryRecord]) -> pd.DataFrame:
    """Converts a list of TelemetryRecords into a pandas DataFrame."""
    flattened = [flatten_telemetry_record(r) for r in records]
    return pd.DataFrame(flattened)


def dataframe_to_records(df: pd.DataFrame) -> List[TelemetryRecord]:
    """Converts a pandas DataFrame back into a list of strictly validated TelemetryRecords."""
    records: List[TelemetryRecord] = []
    errors: List[str] = []

    for idx, row in df.iterrows():
        try:
            record = unflatten_row_to_telemetry_record(row.to_dict())
            records.append(record)
        except (ValidationError, ValueError, KeyError) as e:
            errors.append(f"Row {idx}: {str(e)}")

    if errors:
        raise ValueError(
            f"Failed to validate {len(errors)} records from DataFrame:\n" + "\n".join(errors[:10])
        )

    return records


def export_dataset_to_csv(df: pd.DataFrame, filepath: Union[str, Path]) -> str:
    """Exports validated telemetry DataFrame to CSV."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return str(path.resolve())


def export_dataset_to_parquet(df: pd.DataFrame, filepath: Union[str, Path]) -> str:
    """Exports validated telemetry DataFrame to Parquet."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    return str(path.resolve())


def load_and_validate_csv(filepath: Union[str, Path]) -> List[TelemetryRecord]:
    """Reads a CSV file and validates every record against the Pydantic schema."""
    df = pd.read_csv(filepath)
    return dataframe_to_records(df)


def load_and_validate_parquet(filepath: Union[str, Path]) -> List[TelemetryRecord]:
    """Reads a Parquet file and validates every record against the Pydantic schema."""
    df = pd.read_parquet(filepath, engine="pyarrow")
    return dataframe_to_records(df)
