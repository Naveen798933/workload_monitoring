"""Discrete-time Stateful Performance Simulation Engine.

Integrates:
- Incoming workload traffic feeding into RequestQueue
- Elastic WorkerPool dispatch and concurrency management
- Variable processing latency distributions (lognormal, normal, exponential)
- System telemetry recording (throughput, percentiles, resources, backpressure)
- Production-grade schema validation
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from interface.schema import (
    DropReasonEnum,
    LatencyDistributionRecord,
    QueueTelemetryRecord,
    ResourceUtilizationRecord,
    TelemetryRecord,
    WorkerStateEnum,
    WorkerTelemetryRecord,
)
from interface.validator import records_to_dataframe
from model.queue_system import QueuedRequest, RequestQueue
from model.worker_pool import WorkerPool


class SimulationEngine:
    """Stateful simulation engine coordinating workload arrival, queue, and worker execution."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        random_seed: Optional[int] = None,
    ):
        self.config = config or {}
        sim_cfg = self.config.get("simulation", {})
        res_cfg = self.config.get("resource_model", {})
        q_cfg = res_cfg.get("queue", {})
        lat_cfg = res_cfg.get("latency_distribution", {})

        self.time_step_sec: float = float(sim_cfg.get("time_step_seconds", 1.0))
        self.random_seed: Optional[int] = random_seed if random_seed is not None else sim_cfg.get("random_seed")

        # Initialize RNG
        if self.random_seed is not None:
            self.rng = np.random.default_rng(self.random_seed)
        else:
            self.rng = np.random.default_rng()

        # Queue subsystem
        self.queue = RequestQueue(
            queue_type=q_cfg.get("queue_type", "FIFO"),
            max_capacity=int(q_cfg.get("max_capacity", 500)),
            drop_policy=q_cfg.get("drop_policy", "DROP_TAIL"),
            request_timeout_sec=float(q_cfg.get("request_timeout_sec", 5.0)),
        )

        # Worker cluster
        self.worker_pool = WorkerPool(config=self.config)

        # Latency parameters
        self.lat_dist: str = str(lat_cfg.get("distribution", "lognormal")).lower()
        self.base_service_time_ms: float = float(lat_cfg.get("base_service_time_ms", 28.0))
        self.service_time_std_dev_ms: float = float(lat_cfg.get("service_time_std_dev_ms", 8.0))
        self.min_latency_ms: float = float(lat_cfg.get("min_latency_ms", 5.0))
        self.max_latency_ms: float = float(lat_cfg.get("max_latency_ms", 3000.0))
        self.concurrency_penalty: float = float(lat_cfg.get("concurrency_penalty_factor", 0.05))

        self.request_seq: int = 0

    def _sample_service_latency_ms(self, worker_load_factor: float) -> float:
        """Samples service latency from configured distribution with concurrency load penalty."""
        # Penalty scales up non-linearly under heavy worker saturation
        penalty_mult = 1.0 + (self.concurrency_penalty * math.exp(min(worker_load_factor, 2.5)))

        if self.lat_dist == "normal":
            raw = self.rng.normal(self.base_service_time_ms, self.service_time_std_dev_ms)
        elif self.lat_dist == "exponential":
            raw = self.rng.exponential(self.base_service_time_ms)
        else:
            # Lognormal distribution
            mu = math.log(max(1.0, self.base_service_time_ms))
            sigma = max(0.1, self.service_time_std_dev_ms / max(1.0, self.base_service_time_ms))
            raw = self.rng.lognormal(mu, sigma)

        adjusted = raw * penalty_mult
        return float(np.clip(adjusted, self.min_latency_ms, self.max_latency_ms))

    def step(self, current_time: float, incoming_rate_rps: float) -> TelemetryRecord:
        """Executes a single discrete simulation step of length time_step_sec."""
        # 1. Update worker lifecycle (cold starts, warm ups, drains)
        self.worker_pool.update_lifecycle(current_time)

        # 2. Number of incoming requests in this interval
        num_incoming = int(round(incoming_rate_rps * self.time_step_sec))
        dropped_in_step = 0
        primary_drop_reason = DropReasonEnum.NONE

        # 3. Enqueue all arriving requests
        for _ in range(num_incoming):
            self.request_seq += 1
            req_id = f"req-{self.request_seq}"
            req = QueuedRequest.create(
                request_id=req_id,
                arrival_time=current_time,
                timeout_sec=self.queue.request_timeout_sec,
            )
            accepted, dropped_req, reason = self.queue.enqueue(req, current_time)
            if not accepted:
                dropped_in_step += 1
                primary_drop_reason = reason

        # 4. Check for expired requests in queue
        expired = self.queue.purge_expired(current_time)
        if expired:
            dropped_in_step += len(expired)
            if primary_drop_reason == DropReasonEnum.NONE:
                primary_drop_reason = DropReasonEnum.TIMEOUT

        # 5. Dispatch queued requests to ready workers
        ready_workers = self.worker_pool.get_ready_workers()
        total_capacity_rps = self.worker_pool.get_total_capacity_rps()
        max_processable_in_step = int(total_capacity_rps * self.time_step_sec)

        served_latencies_ms: List[float] = []
        queue_wait_times_sec: List[float] = []
        served_count = 0

        # Calculate current load factor across ready workers
        active_ratio = self.worker_pool.compute_cpu_utilization()

        while served_count < max_processable_in_step and self.queue.depth > 0:
            req = self.queue.dequeue(current_time)
            if req is None:
                break

            wait_sec = max(0.0, current_time - req.arrival_time)
            queue_wait_times_sec.append(wait_sec)

            service_ms = self._sample_service_latency_ms(active_ratio)
            total_latency_ms = (wait_sec * 1000.0) + service_ms
            served_latencies_ms.append(total_latency_ms)
            served_count += 1

        # 6. Update worker in-flight load counters based on served vs capacity
        if ready_workers:
            per_worker_concurrency = int(
                round((served_count / max(1, len(ready_workers))) * (self.base_service_time_ms / 1000.0))
            )
            for w in ready_workers:
                w.active_requests = min(w.max_concurrency, per_worker_concurrency)
                w.total_served += served_count // len(ready_workers)

        # 7. Compute latency distribution percentiles
        if served_latencies_ms:
            sorted_lat = sorted(served_latencies_ms)
            p_min = float(sorted_lat[0])
            p_mean = float(np.mean(sorted_lat))
            p_50 = float(np.percentile(sorted_lat, 50))
            p_90 = float(np.percentile(sorted_lat, 90))
            p_95 = float(np.percentile(sorted_lat, 95))
            p_99 = float(np.percentile(sorted_lat, 99))
            p_max = float(sorted_lat[-1])
        else:
            # Baseline when no requests served
            p_min = self.base_service_time_ms
            p_mean = self.base_service_time_ms
            p_50 = self.base_service_time_ms
            p_90 = self.base_service_time_ms
            p_95 = self.base_service_time_ms
            p_99 = self.base_service_time_ms
            p_max = self.base_service_time_ms

        latency_record = LatencyDistributionRecord(
            min_ms=round(p_min, 2),
            mean_ms=round(p_mean, 2),
            p50_ms=round(p_50, 2),
            p90_ms=round(p_90, 2),
            p95_ms=round(p_95, 2),
            p99_ms=round(p_99, 2),
            max_ms=round(p_max, 2),
        )

        # 8. Compute resources
        cpu_util = self.worker_pool.compute_cpu_utilization()
        mem_used, mem_total, mem_ratio = self.worker_pool.compute_memory_metrics()
        total_cores = sum(w.cpu_cores for w in self.worker_pool.workers)

        resource_record = ResourceUtilizationRecord(
            cpu_utilization_ratio=round(cpu_util, 4),
            memory_used_mb=round(mem_used, 2),
            memory_total_mb=round(mem_total, 2),
            memory_utilization_ratio=round(mem_ratio, 4),
            allocated_cpu_cores=round(total_cores, 1),
        )

        # 9. Compute queue metrics
        q_wait_p95 = float(np.percentile(queue_wait_times_sec, 95)) if queue_wait_times_sec else 0.0
        queue_record = QueueTelemetryRecord(
            queue_depth=self.queue.depth,
            max_capacity=self.queue.max_capacity,
            queue_wait_p95_sec=round(q_wait_p95, 4),
            dropped_count=dropped_in_step,
            drop_reason=primary_drop_reason if dropped_in_step > 0 else DropReasonEnum.NONE,
        )

        # 10. Compute worker states
        total_workers = len(self.worker_pool.workers)
        ready_count = len([w for w in self.worker_pool.workers if w.state == WorkerStateEnum.READY])
        busy_count = len([w for w in self.worker_pool.workers if w.state == WorkerStateEnum.BUSY])
        init_count = len([
            w for w in self.worker_pool.workers
            if w.state in (WorkerStateEnum.INITIALIZING, WorkerStateEnum.WARMING_UP)
        ])
        drain_count = len([w for w in self.worker_pool.workers if w.state == WorkerStateEnum.DRAINING])

        worker_record = WorkerTelemetryRecord(
            total_workers=total_workers,
            ready_workers=ready_count,
            busy_workers=busy_count,
            initializing_workers=init_count,
            draining_workers=drain_count,
            current_capacity_rps=round(total_capacity_rps, 2),
        )

        # 11. Rates and error accounting
        served_rate = served_count / self.time_step_sec
        dropped_rate = dropped_in_step / self.time_step_sec
        total_finished = served_rate + dropped_rate
        err_rate = (dropped_rate / max(1e-6, total_finished)) if total_finished > 0 else 0.0

        # Auto-scaling check
        self.worker_pool.evaluate_autoscaling(current_time, cpu_util, self.queue.depth)

        return TelemetryRecord(
            timestamp=round(current_time, 2),
            request_rate_rps=round(incoming_rate_rps, 2),
            served_rate_rps=round(served_rate, 2),
            dropped_rate_rps=round(dropped_rate, 2),
            error_count=dropped_in_step,
            error_rate=round(min(1.0, err_rate), 4),
            latency=latency_record,
            resources=resource_record,
            queue=queue_record,
            workers=worker_record,
        )

    def run_simulation(self, workload_df: pd.DataFrame) -> List[TelemetryRecord]:
        """Runs the engine over the workload timeline and returns validated TelemetryRecords."""
        records: List[TelemetryRecord] = []
        for _, row in workload_df.iterrows():
            rec = self.step(
                current_time=float(row["timestamp"]),
                incoming_rate_rps=float(row["request_rate_rps"]),
            )
            records.append(rec)
        return records
