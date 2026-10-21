"""Vercel api/ entrypoint for Serverless Functions."""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from monitoring.exporter_server import MetricsHandler, WorkloadMetricsServer

_server = WorkloadMetricsServer()
MetricsHandler.server_instance = _server


class handler(MetricsHandler):
    """Vercel native Python Serverless Function HTTP Handler."""
    pass


app = handler
