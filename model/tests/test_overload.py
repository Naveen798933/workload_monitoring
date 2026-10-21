"""Stress and Overload Testing for Queue Saturation, Drop Policies, and Error Rates."""

import pytest
from interface.schema import DropReasonEnum
from model.queue_system import QueuedRequest, RequestQueue
from model.engine import SimulationEngine
from simulator.config import load_config


def test_drop_tail_policy():
    """Verify DROP_TAIL rejects new arrivals when queue hits max capacity."""
    q = RequestQueue(queue_type="FIFO", max_capacity=3, drop_policy="DROP_TAIL")

    for i in range(3):
        accepted, dropped, reason = q.enqueue(QueuedRequest.create(f"req-{i}", arrival_time=1.0), current_time=1.0)
        assert accepted
        assert dropped is None

    # 4th request must be rejected
    accepted, dropped, reason = q.enqueue(QueuedRequest.create("overflow-req", arrival_time=1.0), current_time=1.0)
    assert not accepted
    assert dropped.request_id == "overflow-req"
    assert reason == DropReasonEnum.QUEUE_OVERFLOW
    assert q.depth == 3


def test_drop_head_policy():
    """Verify DROP_HEAD evicts oldest request to accommodate incoming request."""
    q = RequestQueue(queue_type="FIFO", max_capacity=2, drop_policy="DROP_HEAD")

    q.enqueue(QueuedRequest.create("req-first", arrival_time=1.0), current_time=1.0)
    q.enqueue(QueuedRequest.create("req-second", arrival_time=1.0), current_time=1.0)

    # 3rd request should evict req-first
    accepted, dropped, reason = q.enqueue(QueuedRequest.create("req-new", arrival_time=1.1), current_time=1.1)
    assert accepted
    assert dropped.request_id == "req-first"
    assert reason == DropReasonEnum.QUEUE_OVERFLOW
    assert q.depth == 2
    assert q.dequeue(current_time=1.2).request_id == "req-second"
    assert q.dequeue(current_time=1.2).request_id == "req-new"


def test_request_timeout_expiration():
    """Verify requests lingering in queue past timeout deadline are purged."""
    q = RequestQueue(queue_type="FIFO", max_capacity=10, request_timeout_sec=2.0)
    q.enqueue(QueuedRequest.create("stale-req", arrival_time=1.0, timeout_sec=2.0), current_time=1.0)

    # At t=2.5 (1.5s elapsed): not expired yet
    expired = q.purge_expired(current_time=2.5)
    assert len(expired) == 0
    assert q.depth == 1

    # At t=3.5 (2.5s elapsed): expired
    expired = q.purge_expired(current_time=3.5)
    assert len(expired) == 1
    req, reason = expired[0]
    assert req.request_id == "stale-req"
    assert reason == DropReasonEnum.TIMEOUT
    assert q.depth == 0


def test_engine_overload_behavior():
    """Simulate severe overload (500 RPS on a 100 RPS capacity cluster)."""
    config = load_config()
    # Configure tiny queue to force rapid saturation
    config["resource_model"]["queue"]["max_capacity"] = 50
    config["resource_model"]["worker_pool"]["initial_workers"] = 2
    config["resource_model"]["worker_pool"]["throughput_per_worker_rps"] = 25.0
    config["resource_model"]["worker_pool"]["auto_scaling"]["enabled"] = False

    engine = SimulationEngine(config=config, random_seed=42)

    # Step with 500 RPS incoming load
    record = engine.step(current_time=1.0, incoming_rate_rps=500.0)

    assert record.dropped_rate_rps > 0
    assert record.error_count > 0
    assert record.error_rate > 0.0
    assert record.queue.dropped_count > 0
    assert record.queue.drop_reason in (DropReasonEnum.QUEUE_OVERFLOW, DropReasonEnum.TIMEOUT)
