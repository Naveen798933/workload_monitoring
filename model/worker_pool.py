"""Worker Pool lifecycle and resource modeling engine.

Simulates:
- Worker CPU cores, memory allocation, and per-worker throughput capacity
- Concurrency limits and saturation penalties
- Dynamic scaling with realistic cold-start, warm-up, and graceful drain latencies
- Resource utilization metrics (CPU cores utilization, memory footprint)
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, Tuple
from interface.schema import WorkerStateEnum


class WorkerInstance:
    """Represents a discrete compute worker container/node."""

    def __init__(
        self,
        worker_id: str,
        current_time: float,
        cpu_cores: float = 2.0,
        memory_mb: float = 2048.0,
        throughput_rps: float = 25.0,
        max_concurrency: int = 30,
        cold_start_delay_sec: float = 5.0,
        warm_up_delay_sec: float = 2.0,
        graceful_drain_delay_sec: float = 3.0,
    ):
        self.worker_id = worker_id
        self.cpu_cores = cpu_cores
        self.memory_mb = memory_mb
        self.throughput_rps = throughput_rps
        self.max_concurrency = max_concurrency

        self.cold_start_delay_sec = cold_start_delay_sec
        self.warm_up_delay_sec = warm_up_delay_sec
        self.graceful_drain_delay_sec = graceful_drain_delay_sec

        self.created_at = current_time
        self.ready_at = current_time + cold_start_delay_sec + warm_up_delay_sec
        self.state = WorkerStateEnum.INITIALIZING
        self.draining_started_at: Optional[float] = None

        self.active_requests: int = 0
        self.total_served: int = 0

    def update_lifecycle(self, current_time: float) -> None:
        """Transitions worker state based on elapsed time and current conditions."""
        if self.state == WorkerStateEnum.INITIALIZING:
            if current_time >= (self.created_at + self.cold_start_delay_sec):
                self.state = WorkerStateEnum.WARMING_UP

        if self.state == WorkerStateEnum.WARMING_UP:
            if current_time >= self.ready_at:
                self.state = WorkerStateEnum.READY

        if self.state == WorkerStateEnum.READY and self.active_requests > 0:
            self.state = WorkerStateEnum.BUSY
        elif self.state == WorkerStateEnum.BUSY and self.active_requests == 0:
            self.state = WorkerStateEnum.READY

        if self.state == WorkerStateEnum.DRAINING:
            # Drain completes when requests reach 0 or timeout expires
            drain_deadline = (self.draining_started_at or current_time) + self.graceful_drain_delay_sec
            if self.active_requests == 0 or current_time >= drain_deadline:
                self.state = WorkerStateEnum.STOPPED

    def initiate_drain(self, current_time: float) -> None:
        """Initiates graceful shutdown."""
        if self.state not in (WorkerStateEnum.DRAINING, WorkerStateEnum.STOPPED):
            self.state = WorkerStateEnum.DRAINING
            self.draining_started_at = current_time

    @property
    def is_available(self) -> bool:
        """Can accept new incoming requests."""
        return self.state in (WorkerStateEnum.READY, WorkerStateEnum.BUSY) and (
            self.active_requests < self.max_concurrency
        )


class WorkerPool:
    """Manages an elastic cluster of worker instances."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        wp_cfg = cfg.get("resource_model", {}).get("worker_pool", {})

        self.min_workers: int = int(wp_cfg.get("min_workers", 1))
        self.max_workers: int = int(wp_cfg.get("max_workers", 16))
        self.initial_workers: int = int(wp_cfg.get("initial_workers", 4))
        self.cpu_cores_per_worker: float = float(wp_cfg.get("cpu_cores_per_worker", 2.0))
        self.memory_mb_per_worker: float = float(wp_cfg.get("memory_mb_per_worker", 2048.0))
        self.throughput_per_worker_rps: float = float(wp_cfg.get("throughput_per_worker_rps", 25.0))
        self.max_concurrency_per_worker: int = int(wp_cfg.get("max_concurrency_per_worker", 30))

        self.cold_start_delay_sec: float = float(wp_cfg.get("cold_start_delay_sec", 5.0))
        self.warm_up_delay_sec: float = float(wp_cfg.get("warm_up_delay_sec", 2.0))
        self.graceful_drain_delay_sec: float = float(wp_cfg.get("graceful_drain_delay_sec", 3.0))

        auto_scale_cfg = wp_cfg.get("auto_scaling", {})
        self.auto_scaling_enabled: bool = bool(auto_scale_cfg.get("enabled", True))
        self.target_cpu_utilization: float = float(auto_scale_cfg.get("target_cpu_utilization", 0.75))
        self.scale_up_step: int = int(auto_scale_cfg.get("scale_up_step", 2))
        self.scale_down_step: int = int(auto_scale_cfg.get("scale_down_step", 1))
        self.cooldown_period_sec: float = float(auto_scale_cfg.get("cooldown_period_sec", 10.0))

        self.last_scale_action_time: float = -self.cooldown_period_sec
        self.workers: List[WorkerInstance] = []

        # Boot initial workers (ready immediately at t=0 to avoid cold-start drop at t=0)
        self._bootstrap_initial_workers()

    def _bootstrap_initial_workers(self) -> None:
        """Initializes the baseline worker set."""
        for _ in range(self.initial_workers):
            w = WorkerInstance(
                worker_id=str(uuid.uuid4())[:8],
                current_time=0.0,
                cpu_cores=self.cpu_cores_per_worker,
                memory_mb=self.memory_mb_per_worker,
                throughput_rps=self.throughput_per_worker_rps,
                max_concurrency=self.max_concurrency_per_worker,
                cold_start_delay_sec=self.cold_start_delay_sec,
                warm_up_delay_sec=self.warm_up_delay_sec,
                graceful_drain_delay_sec=self.graceful_drain_delay_sec,
            )
            # Baseline initial workers start ready
            w.state = WorkerStateEnum.READY
            w.ready_at = 0.0
            self.workers.append(w)

    def spawn_worker(self, current_time: float) -> WorkerInstance:
        """Provisions a new worker with cold-start latency."""
        w = WorkerInstance(
            worker_id=str(uuid.uuid4())[:8],
            current_time=current_time,
            cpu_cores=self.cpu_cores_per_worker,
            memory_mb=self.memory_mb_per_worker,
            throughput_rps=self.throughput_per_worker_rps,
            max_concurrency=self.max_concurrency_per_worker,
            cold_start_delay_sec=self.cold_start_delay_sec,
            warm_up_delay_sec=self.warm_up_delay_sec,
            graceful_drain_delay_sec=self.graceful_drain_delay_sec,
        )
        self.workers.append(w)
        return w

    def scale_up(self, count: int, current_time: float) -> int:
        """Scales out additional workers up to max_workers limit."""
        active_and_init = len([w for w in self.workers if w.state != WorkerStateEnum.STOPPED])
        allowable = max(0, self.max_workers - active_and_init)
        to_add = min(count, allowable)

        for _ in range(to_add):
            self.spawn_worker(current_time)

        if to_add > 0:
            self.last_scale_action_time = current_time

        return to_add

    def scale_down(self, count: int, current_time: float) -> int:
        """Initiates graceful drain of idle or ready workers down to min_workers."""
        ready_workers = [w for w in self.workers if w.state == WorkerStateEnum.READY]
        active_count = len([w for w in self.workers if w.state not in (WorkerStateEnum.DRAINING, WorkerStateEnum.STOPPED)])
        allowable = max(0, active_count - self.min_workers)
        to_remove = min(count, allowable, len(ready_workers))

        for i in range(to_remove):
            ready_workers[i].initiate_drain(current_time)

        if to_remove > 0:
            self.last_scale_action_time = current_time

        return to_remove

    def update_lifecycle(self, current_time: float) -> None:
        """Updates states for all workers and prunes fully stopped workers."""
        for w in self.workers:
            w.update_lifecycle(current_time)

        # Retain non-stopped workers or keep at least min_workers
        self.workers = [w for w in self.workers if w.state != WorkerStateEnum.STOPPED]

    def evaluate_autoscaling(self, current_time: float, current_cpu_util: float, queue_depth: int) -> None:
        """Evaluates auto-scaling triggers if cooldown has expired."""
        if not self.auto_scaling_enabled:
            return

        if (current_time - self.last_scale_action_time) < self.cooldown_period_sec:
            return

        # Scale UP conditions: high CPU OR substantial queue backlog
        if current_cpu_util >= self.target_cpu_utilization or queue_depth > 10:
            self.scale_up(self.scale_up_step, current_time)
        # Scale DOWN conditions: very low CPU AND empty queue
        elif current_cpu_util < (self.target_cpu_utilization * 0.4) and queue_depth == 0:
            self.scale_down(self.scale_down_step, current_time)

    def get_ready_workers(self) -> List[WorkerInstance]:
        return [w for w in self.workers if w.state in (WorkerStateEnum.READY, WorkerStateEnum.BUSY)]

    def get_total_capacity_rps(self) -> float:
        """Aggregate throughput capacity of operational workers."""
        ready_count = len(self.get_ready_workers())
        return ready_count * self.throughput_per_worker_rps

    def compute_cpu_utilization(self) -> float:
        """Computes aggregate CPU utilization ratio (0.0 to 1.0)."""
        ready = self.get_ready_workers()
        if not ready:
            return 0.0

        total_concurrency_slots = sum(w.max_concurrency for w in ready)
        if total_concurrency_slots == 0:
            return 0.0

        active_slots = sum(w.active_requests for w in ready)
        # Ratio of active concurrency slots, with non-zero idle baseline (e.g., 2% system idle)
        base_idle = 0.02
        raw_ratio = base_idle + (1.0 - base_idle) * (active_slots / total_concurrency_slots)
        return float(min(1.0, max(0.0, raw_ratio)))

    def compute_memory_metrics(self) -> Tuple[float, float, float]:
        """Computes (memory_used_mb, memory_total_mb, memory_utilization_ratio)."""
        active_workers = [w for w in self.workers if w.state != WorkerStateEnum.STOPPED]
        if not active_workers:
            return 0.0, 1024.0, 0.0

        total_mb = sum(w.memory_mb for w in active_workers)
        # Base OS/Runtime overhead: ~15% per worker
        base_overhead_mb = sum(w.memory_mb * 0.15 for w in active_workers)
        # Per-in-flight request buffer allocation (~2MB per concurrent request)
        active_reqs = sum(w.active_requests for w in active_workers)
        dynamic_req_mb = active_reqs * 2.0

        used_mb = min(total_mb, base_overhead_mb + dynamic_req_mb)
        ratio = used_mb / total_mb if total_mb > 0 else 0.0
        return float(round(used_mb, 2)), float(round(total_mb, 2)), float(round(ratio, 4))
