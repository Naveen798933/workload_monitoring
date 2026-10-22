"""Vercel api/ entrypoint for Serverless Functions."""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure safe writable directory for Matplotlib cache on AWS Lambda / Vercel
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from monitoring.exporter_server import wsgi_app, MetricsHandler

# Universal WSGI application entrypoint for Vercel
app = wsgi_app
application = wsgi_app

# BaseHTTPRequestHandler class for Vercel
handler = MetricsHandler
