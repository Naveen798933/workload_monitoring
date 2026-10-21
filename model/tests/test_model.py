"""Unit tests for Resource and Performance Model (Workers, Queues, Latency)."""

import pytest
from interface.schema import DropReasonEnum, WorkerStateEnum
from model.queue_system import QueuedRequest, RequestQueue
from model.worker_pool import WorkerInstance, WorkerPool


def test_fifo_queue_ordering():
    """Verify strictly FIFO delivery of requests."""
    q = RequestQueue(queue_type="FIFO", max_capacity=10)
    q.enqueue(QueuedRequest.create("req-1", arrival_time=1.0), current_time=1.0)
    q.enqueue(QueuedRequest.create("req-2", arrival_time=2.0), current_time=2.0)
    q.enqueue(QueuedRequest.create("req-3", arrival_time=3.0), current_time=3.0)

    assert q.depth == 3
    assert q.dequeue(current_time=3.5).request_id == "req-1"
    assert q.dequeue(current_time=3.5).request_id == "req-2"
    assert q.dequeue(current_time=3.5).request_id == "req-3"
    assert q.depth == 0


def test_priority_queue_ordering():
    """Verify requests with higher priority (lower numerical value) dequeue first."""
    q = RequestQueue(queue_type="PRIORITY", max_capacity=10)
    q.enqueue(QueuedRequest.create("low-pri", arrival_time=1.0, priority=10), current_time=1.0)
    q.enqueue(QueuedRequest.create("high-pri", arrival_time=1.5, priority=1), current_time=1.5)
    q.enqueue(QueuedRequest.create("med-pri", arrival_time=2.0, priority=5), current_time=2.0)

    assert q.dequeue(current_time=2.5).request_id == "high-pri"
    assert q.dequeue(current_time=2.5).request_id == "med-pri"
    assert q.dequeue(current_time=2.5).request_id == "low-pri"


def test_worker_cold_start_lifecycle():
    """Verify worker transitions: INITIALIZING -> WARMING_UP -> READY."""
    w = WorkerInstance(
        worker_id="test-w1",
        current_time=0.0,
        cold_start_delay_sec=5.0,
        warm_up_delay_sec=2.0,
        graceful_drain_delay_sec=3.0,
    )

    assert w.state == WorkerStateEnum.INITIALIZING
    assert not w.is_available

    # At t=4.0: still initializing
    w.update_lifecycle(current_time=4.0)
    assert w.state == WorkerStateEnum.INITIALIZING

    # At t=5.1: transitions to warming up
    w.update_lifecycle(current_time=5.1)
    assert w.state == WorkerStateEnum.WARMING_UP
    assert not w.is_available

    # At t=7.1: transitions to ready
    w.update_lifecycle(current_time=7.1)
    assert w.state == WorkerStateEnum.READY
    assert w.is_available


def test_worker_graceful_drain():
    """Verify worker drains active requests before entering STOPPED state."""
    w = WorkerInstance(
        worker_id="drain-w1",
        current_time=0.0,
        cold_start_delay_sec=0.0,
        warm_up_delay_sec=0.0,
        graceful_drain_delay_sec=4.0,
    )
    w.state = WorkerStateEnum.READY
    w.active_requests = 2

    w.initiate_drain(current_time=10.0)
    assert w.state == WorkerStateEnum.DRAINING

    # Drain while requests are still in-flight
    w.update_lifecycle(current_time=12.0)
    assert w.state == WorkerStateEnum.DRAINING

    # Requests complete: worker transitions to STOPPED
    w.active_requests = 0
    w.update_lifecycle(current_time=12.5)
    assert w.state == WorkerStateEnum.STOPPED


def test_worker_pool_autoscaling():
    """Verify worker pool scales out under simulated CPU/queue pressure."""
    pool = WorkerPool(config={
        "resource_model": {
            "worker_pool": {
                "initial_workers": 2,
                "min_workers": 1,
                "max_workers": 8,
                "cold_start_delay_sec": 0.0,
                "warm_up_delay_sec": 0.0,
                "auto_scaling": {
                    "enabled": True,
                    "target_cpu_utilization": 0.70,
                    "scale_up_step": 2,
                    "cooldown_period_sec": 5.0,
                },
            }
        }
    })

    assert len(pool.workers) == 2

    # High CPU trigger
    pool.evaluate_autoscaling(current_time=1.0, current_cpu_util=0.85, queue_depth=15)
    assert len(pool.workers) == 4

    # Cooldown blocks immediate second scale up
    pool.evaluate_autoscaling(current_time=2.0, current_cpu_util=0.90, queue_depth=20)
    assert len(pool.workers) == 4

    # After cooldown expires, can scale up again
    pool.evaluate_autoscaling(current_time=7.0, current_cpu_util=0.85, queue_depth=20)
    assert len(pool.workers) == 6
