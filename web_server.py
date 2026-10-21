"""Root entry point for the Interactive Localhost Web Dashboard & Exporter."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitoring.exporter_server import WorkloadMetricsServer

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    print("=" * 80)
    print(f"[*] Starting Workload Simulation Web Dashboard on http://localhost:{port}/")
    print(f"[*] Prometheus Metrics available at http://localhost:{port}/metrics")
    print("=" * 80)

    server = WorkloadMetricsServer(host="0.0.0.0", port=port)
    server.start(background=False)
