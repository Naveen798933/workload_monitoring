"""Configurable Request Queue simulation with FIFO, Priority, and custom drop policies.

Supports:
- FIFO and Priority Queues
- Configurable maximum backlog capacity
- Drop policies: DROP_TAIL (discard incoming), DROP_HEAD (discard oldest), REJECT (immediate 503)
- Request timeout handling and expiration purging
"""

from __future__ import annotations
from dataclasses import dataclass, field
import heapq
from typing import Any, Dict, List, Optional, Tuple
from interface.schema import DropReasonEnum


import threading


@dataclass(order=True)
class QueuedRequest:
    """Represents an in-flight or waiting transaction in the simulation."""
    # Priority queue compares tuple (sort_index, arrival_time)
    sort_index: int
    arrival_time: float = field(compare=True)
    request_id: str = field(compare=False)
    priority: int = field(compare=False, default=1)
    service_time_sec: float = field(compare=False, default=0.03)
    timeout_sec: float = field(compare=False, default=5.0)

    @classmethod
    def create(
        cls,
        request_id: str,
        arrival_time: float,
        priority: int = 1,
        service_time_sec: float = 0.03,
        timeout_sec: float = 5.0,
    ) -> QueuedRequest:
        # Lower numerical priority value = higher precedence
        return cls(
            sort_index=priority,
            arrival_time=arrival_time,
            request_id=request_id,
            priority=priority,
            service_time_sec=service_time_sec,
            timeout_sec=timeout_sec,
        )


class RequestQueue:
    """Thread-safe stateful queue simulating buffer backpressure."""

    def __init__(
        self,
        queue_type: str = "FIFO",
        max_capacity: int = 500,
        drop_policy: str = "DROP_TAIL",
        request_timeout_sec: float = 5.0,
    ):
        self.queue_type = queue_type.upper()
        self.max_capacity = max(1, max_capacity)
        self.drop_policy = drop_policy.upper()
        self.request_timeout_sec = request_timeout_sec

        self._items: List[QueuedRequest] = []
        self._counter: int = 0
        self._lock = threading.RLock()

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def is_full(self) -> bool:
        with self._lock:
            return len(self._items) >= self.max_capacity

    def purge_expired(self, current_time: float) -> List[Tuple[QueuedRequest, DropReasonEnum]]:
        """Purges requests that have exceeded their timeout deadline."""
        with self._lock:
            surviving: List[QueuedRequest] = []
            expired: List[Tuple[QueuedRequest, DropReasonEnum]] = []

            for req in self._items:
                if (current_time - req.arrival_time) > req.timeout_sec:
                    expired.append((req, DropReasonEnum.TIMEOUT))
                else:
                    surviving.append(req)

            self._items = surviving
            if self.queue_type == "PRIORITY":
                heapq.heapify(self._items)

            return expired

    def enqueue(
        self,
        request: QueuedRequest,
        current_time: float,
    ) -> Tuple[bool, Optional[QueuedRequest], DropReasonEnum]:
        """Attempts to enqueue a request according to max capacity and drop policy.

        Returns:
            Tuple of (accepted: bool, dropped_request: Optional[QueuedRequest], reason: DropReasonEnum)
        """
        with self._lock:
            # Purge stale requests first
            self.purge_expired(current_time)

            if len(self._items) < self.max_capacity:
                if self.queue_type == "PRIORITY":
                    heapq.heappush(self._items, request)
                else:
                    self._items.append(request)
                return True, None, DropReasonEnum.NONE

            # Queue is saturated - execute drop policy
            if self.drop_policy == "DROP_TAIL" or self.drop_policy == "REJECT":
                reason = DropReasonEnum.REJECTED if self.drop_policy == "REJECT" else DropReasonEnum.QUEUE_OVERFLOW
                return False, request, reason

            elif self.drop_policy == "DROP_HEAD":
                # For priority queue, drop the LOWEST priority (highest sort_index) to protect high-pri
                if self.queue_type == "PRIORITY":
                    lowest_pri_idx = max(range(len(self._items)), key=lambda i: self._items[i].sort_index)
                    evicted = self._items.pop(lowest_pri_idx)
                    heapq.heapify(self._items)
                    heapq.heappush(self._items, request)
                else:
                    evicted = self._items.pop(0)
                    self._items.append(request)
                return True, evicted, DropReasonEnum.QUEUE_OVERFLOW

            # Default fallback: reject
            return False, request, DropReasonEnum.QUEUE_OVERFLOW

    def dequeue(self, current_time: float) -> Optional[QueuedRequest]:
        """Pulls the next eligible non-expired request from the queue."""
        with self._lock:
            while self._items:
                if self.queue_type == "PRIORITY":
                    candidate = heapq.heappop(self._items)
                else:
                    candidate = self._items.pop(0)

                # Check if candidate timed out while waiting in queue
                if (current_time - candidate.arrival_time) <= candidate.timeout_sec:
                    return candidate

            return None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
