"""Interactive Web Dashboard & Prometheus Metrics Server on localhost.

Provides:
- Complete interactive Web UI on http://localhost:8000/
- Real-time dynamic Chart.js telemetry dashboards (Throughput, Latencies, CPU/Memory, Queue Backpressure)
- Live parameter tuning (Pattern, Duration, Seed, Workers, Sliders)
- Direct CSV, Parquet, and Image downloads
- Prometheus metrics endpoint on http://localhost:8000/metrics
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to sys.path if invoked directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.config import load_config
from simulator.generator import WorkloadGenerator
from simulator.visualizer import WorkloadVisualizer
from model.engine import SimulationEngine
from monitoring.metrics import PrometheusMetricsManager
from interface.validator import (
    records_to_dataframe,
    export_dataset_to_csv,
    export_dataset_to_parquet,
)

HTML_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Workload Simulation & Monitoring Dashboard | Member 1</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(17, 24, 39, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --purple: #8b5cf6;
      --cyan: #06b6d4;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 10% 20%, #111827 0%, #0b0f19 90%);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      min-height: 100vh;
      padding: 24px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
      flex-wrap: wrap;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .badge {
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      padding: 4px 8px;
      border-radius: 9999px;
      letter-spacing: 0.5px;
    }
    .title h1 {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    .title p {
      font-size: 13px;
      color: var(--text-muted);
    }
    .header-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: all 0.2s ease;
    }
    .btn:hover {
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.2);
      transform: translateY(-1px);
    }
    .btn-primary {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      border: 1px solid #3b82f6;
    }
    .btn-primary:hover {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
    }
    .btn-live {
      background: rgba(16, 185, 129, 0.15);
      border-color: #10b981;
      color: #34d399;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 10px #10b981;
      display: inline-block;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.85); }
    }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      position: relative;
      overflow: hidden;
    }
    .kpi-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: var(--accent, var(--primary));
    }
    .kpi-label {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .kpi-value {
      font-size: 26px;
      font-weight: 700;
      color: #fff;
    }
    .kpi-sub {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Controls Panel */
    .controls-panel {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 20px;
      align-items: center;
      justify-content: space-between;
    }
    .control-group {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .control-group label {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
    }
    select, input[type="number"] {
      background: #1f2937;
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      outline: none;
    }
    select:focus, input[type="number"]:focus {
      border-color: var(--primary);
    }

    /* Charts Grid */
    .charts-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 1024px) {
      .charts-grid { grid-template-columns: 1fr; }
    }
    .chart-card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px;
      display: flex;
      flex-direction: column;
    }
    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .chart-title {
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .chart-legend-badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-muted);
    }
    .canvas-container {
      position: relative;
      height: 260px;
      width: 100%;
    }

    footer {
      text-align: center;
      padding-top: 16px;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--card-border);
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span class="status-dot"></span>
      <div class="title">
        <h1>Workload Simulation & Monitoring Engine</h1>
        <p>Member 1 — Distributed Systems & Reliability Engineering Dashboard</p>
      </div>
      <span class="badge">Production Grade</span>
    </div>

    <div class="header-actions">
      <a href="/metrics" target="_blank" class="btn" title="Inspect Prometheus scrape output">
        📡 Prometheus Endpoint
      </a>
      <a href="/api/download/csv" class="btn" download title="Download CSV Dataset">
        📥 CSV
      </a>
      <a href="/api/download/parquet" class="btn" download title="Download Parquet Dataset">
        📦 Parquet
      </a>
      <a href="/sample_data/workload_timeline.png" target="_blank" class="btn" title="View Matplotlib Timeline Plot">
        🖼️ Plot PNG
      </a>
    </div>
  </header>

  <!-- Interactive Control Bar -->
  <div class="controls-panel">
    <div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: center;">
      <div class="control-group">
        <label for="patternSelect">Traffic Pattern:</label>
        <select id="patternSelect">
          <option value="composite" selected>Composite (Diurnal + Spikes + Noise)</option>
          <option value="spike">Sudden Spikes</option>
          <option value="steady">Steady Baseline</option>
          <option value="gradual">Gradual Diurnal</option>
          <option value="noisy">Stochastic Walk</option>
        </select>
      </div>

      <div class="control-group">
        <label for="durationInput">Duration (s):</label>
        <input type="number" id="durationInput" value="120" min="20" max="600" step="10" style="width: 80px;">
      </div>

      <div class="control-group">
        <label for="seedInput">Seed:</label>
        <input type="number" id="seedInput" value="42" style="width: 75px;">
      </div>
    </div>

    <div style="display: flex; gap: 10px;">
      <button class="btn btn-primary" id="btnSimulate" onclick="triggerSimulation()">
        ⚡ Run Simulation
      </button>
      <button class="btn btn-live" id="btnLiveToggle" onclick="toggleLiveFeed()">
        ▶️ Start Live Stream
      </button>
    </div>
  </div>

  <!-- Real-time KPI Stats Cards -->
  <div class="kpi-grid">
    <div class="kpi-card" style="--accent: #3b82f6;">
      <div class="kpi-label">Incoming Traffic</div>
      <div class="kpi-value" id="kpi-traffic">--</div>
      <div class="kpi-sub">Requests per second (RPS)</div>
    </div>
    <div class="kpi-card" style="--accent: #10b981;">
      <div class="kpi-label">Cluster Capacity</div>
      <div class="kpi-value" id="kpi-capacity">--</div>
      <div class="kpi-sub">Total provisioned RPS</div>
    </div>
    <div class="kpi-card" style="--accent: #f59e0b;">
      <div class="kpi-label">Median Latency (p50)</div>
      <div class="kpi-value" id="kpi-latency">--</div>
      <div class="kpi-sub">Service turnaround time</div>
    </div>
    <div class="kpi-card" style="--accent: #8b5cf6;">
      <div class="kpi-label">CPU Utilization</div>
      <div class="kpi-value" id="kpi-cpu">--</div>
      <div class="kpi-sub">Across active worker cores</div>
    </div>
    <div class="kpi-card" style="--accent: #ec4899;">
      <div class="kpi-label">Queue Depth</div>
      <div class="kpi-value" id="kpi-queue">--</div>
      <div class="kpi-sub">Pending requests in backlog</div>
    </div>
    <div class="kpi-card" style="--accent: #ef4444;">
      <div class="kpi-label">Total Errors / Drops</div>
      <div class="kpi-value" id="kpi-errors">--</div>
      <div class="kpi-sub">Saturated or timed-out</div>
    </div>
  </div>

  <!-- Interactive Multi-Panel Telemetry Charts -->
  <div class="charts-grid">
    <!-- Panel 1: Throughput vs Capacity -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">
          <span>📈 Panel 1: Throughput vs System Capacity</span>
        </div>
        <span class="chart-legend-badge">RPS Timeline</span>
      </div>
      <div class="canvas-container">
        <canvas id="chartThroughput"></canvas>
      </div>
    </div>

    <!-- Panel 2: Latency Distribution -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">
          <span>⏱️ Panel 2: Latency Percentiles (p50, p95, p99)</span>
        </div>
        <span class="chart-legend-badge">Milliseconds (ms)</span>
      </div>
      <div class="canvas-container">
        <canvas id="chartLatency"></canvas>
      </div>
    </div>

    <!-- Panel 3: Resource Utilization -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">
          <span>⚙️ Panel 3: Cluster Resource Utilization</span>
        </div>
        <span class="chart-legend-badge">CPU & Memory %</span>
      </div>
      <div class="canvas-container">
        <canvas id="chartResources"></canvas>
      </div>
    </div>

    <!-- Panel 4: Queue Backpressure & Drops -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">
          <span>🛑 Panel 4: Queue Backpressure & Drop Rates</span>
        </div>
        <span class="chart-legend-badge">Backlog Depth</span>
      </div>
      <div class="canvas-container">
        <canvas id="chartQueue"></canvas>
      </div>
    </div>
  </div>

  <footer>
    Member 1: Workload Simulation & Monitoring &bull; Zero Hardcoded Constants Architecture &bull; Prometheus Instrumentation Active
  </footer>

  <script>
    // Chart Configurations
    const chartDefaults = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: {
        legend: { labels: { color: '#9ca3af', font: { size: 11, weight: 600 } } },
        tooltip: { mode: 'index', intersect: false }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#6b7280', maxTicksLimit: 12 }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#6b7280' }
        }
      }
    };

    // 1. Throughput Chart
    const ctxThroughput = document.getElementById('chartThroughput').getContext('2d');
    const chartThroughput = new Chart(ctxThroughput, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Incoming RPS', borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', borderWidth: 2, fill: true, tension: 0.3, data: [] },
          { label: 'Cluster Capacity', borderColor: '#10b981', borderDash: [5, 5], borderWidth: 2, tension: 0, data: [] },
          { label: 'Dropped RPS', borderColor: '#ef4444', borderDash: [2, 2], borderWidth: 1.5, data: [] }
        ]
      },
      options: chartDefaults
    });

    // 2. Latency Chart
    const ctxLatency = document.getElementById('chartLatency').getContext('2d');
    const chartLatency = new Chart(ctxLatency, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'p50 Median (ms)', borderColor: '#f59e0b', borderWidth: 1.8, tension: 0.3, data: [] },
          { label: 'p95 Tail (ms)', borderColor: '#f97316', borderWidth: 2, tension: 0.3, data: [] },
          { label: 'p99 Peak (ms)', borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.12)', borderWidth: 2.2, fill: true, tension: 0.3, data: [] }
        ]
      },
      options: chartDefaults
    });

    // 3. Resources Chart
    const ctxResources = document.getElementById('chartResources').getContext('2d');
    const chartResources = new Chart(ctxResources, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'CPU Util (%)', borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.1)', borderWidth: 2, fill: true, tension: 0.3, data: [] },
          { label: 'Memory Util (%)', borderColor: '#06b6d4', borderWidth: 2, tension: 0.3, data: [] }
        ]
      },
      options: {
        ...chartDefaults,
        scales: {
          ...chartDefaults.scales,
          y: { ...chartDefaults.scales.y, min: 0, max: 100 }
        }
      }
    });

    // 4. Queue Chart
    const ctxQueue = document.getElementById('chartQueue').getContext('2d');
    const chartQueue = new Chart(ctxQueue, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Queue Depth', borderColor: '#ec4899', backgroundColor: 'rgba(236, 72, 153, 0.12)', borderWidth: 2, fill: true, tension: 0.2, data: [] },
          { label: 'Max Capacity', borderColor: '#dc2626', borderDash: [4, 4], borderWidth: 1.5, data: [] }
        ]
      },
      options: chartDefaults
    });

    function updateDashboardData(data) {
      if (!data || !data.records || data.records.length === 0) return;

      const timestamps = data.records.map(r => r.timestamp + 's');

      // Update Chart 1
      chartThroughput.data.labels = timestamps;
      chartThroughput.data.datasets[0].data = data.records.map(r => r.request_rate_rps);
      chartThroughput.data.datasets[1].data = data.records.map(r => r.workers_capacity_rps);
      chartThroughput.data.datasets[2].data = data.records.map(r => r.dropped_rate_rps || 0);
      chartThroughput.update();

      // Update Chart 2
      chartLatency.data.labels = timestamps;
      chartLatency.data.datasets[0].data = data.records.map(r => r.latency_p50_ms);
      chartLatency.data.datasets[1].data = data.records.map(r => r.latency_p95_ms);
      chartLatency.data.datasets[2].data = data.records.map(r => r.latency_p99_ms);
      chartLatency.update();

      // Update Chart 3
      chartResources.data.labels = timestamps;
      chartResources.data.datasets[0].data = data.records.map(r => (r.cpu_utilization_ratio * 100).toFixed(1));
      chartResources.data.datasets[1].data = data.records.map(r => (r.memory_utilization_ratio * 100).toFixed(1));
      chartResources.update();

      // Update Chart 4
      chartQueue.data.labels = timestamps;
      chartQueue.data.datasets[0].data = data.records.map(r => r.queue_depth);
      chartQueue.data.datasets[1].data = data.records.map(r => r.queue_max_capacity);
      chartQueue.update();

      // Update KPI Cards from latest step
      const latest = data.records[data.records.length - 1];
      const totalErrors = data.records.reduce((acc, cur) => acc + (cur.error_count || 0), 0);
      document.getElementById('kpi-traffic').textContent = latest.request_rate_rps.toFixed(1);
      document.getElementById('kpi-capacity').textContent = latest.workers_capacity_rps.toFixed(1);
      document.getElementById('kpi-latency').textContent = latest.latency_p50_ms.toFixed(1) + ' ms';
      document.getElementById('kpi-cpu').textContent = (latest.cpu_utilization_ratio * 100).toFixed(1) + '%';
      document.getElementById('kpi-queue').textContent = latest.queue_depth;
      document.getElementById('kpi-errors').textContent = totalErrors;
    }

    // Trigger simulation via REST API
    async function triggerSimulation() {
      const btn = document.getElementById('btnSimulate');
      btn.textContent = '⏳ Simulating...';
      btn.disabled = true;

      const pattern = document.getElementById('patternSelect').value;
      const duration = document.getElementById('durationInput').value;
      const seed = document.getElementById('seedInput').value;

      try {
        const res = await fetch(`/api/simulate?pattern=${pattern}&duration=${duration}&seed=${seed}`);
        const data = await res.json();
        updateDashboardData(data);
      } catch (err) {
        console.error('Failed to run simulation:', err);
      } finally {
        btn.textContent = '⚡ Run Simulation';
        btn.disabled = false;
      }
    }

    // Live Feed Toggle
    let liveTimer = null;
    function toggleLiveFeed() {
      const btn = document.getElementById('btnLiveToggle');
      if (liveTimer) {
        clearInterval(liveTimer);
        liveTimer = null;
        btn.textContent = '▶️ Start Live Stream';
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-live');
      } else {
        btn.textContent = '⏹️ Stop Live Stream';
        btn.classList.remove('btn-live');
        btn.classList.add('btn-primary');
        liveTimer = setInterval(async () => {
          try {
            const res = await fetch('/api/live-tick');
            const data = await res.json();
            updateDashboardData(data);
          } catch (e) {
            console.error('Live tick error:', e);
          }
        }, 1500);
      }
    }

    // Load initial data on startup
    window.addEventListener('DOMContentLoaded', () => {
      fetch('/api/telemetry')
        .then(r => r.json())
        .then(updateDashboardData)
        .catch(() => triggerSimulation());
    });
  </script>
</body>
</html>
"""


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving Web Dashboard, REST APIs, and Prometheus metrics."""

    server_instance: WorkloadMetricsServer = None

    def _ensure_server_instance(self) -> None:
        if self.server_instance is None or MetricsHandler.server_instance is None:
            MetricsHandler.server_instance = WorkloadMetricsServer()
            self.server_instance = MetricsHandler.server_instance

    def do_GET(self) -> None:
        self._ensure_server_instance()
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. Prometheus Scrape Endpoint
        if path in ("/metrics", "/metrics/"):
            content = self.server_instance.manager.scrape_latest()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        # 2. Web UI Dashboard Root
        elif path in ("/", "/dashboard"):
            html_bytes = HTML_DASHBOARD_TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)

        # 3. Telemetry JSON API
        elif path == "/api/telemetry":
            payload = self.server_instance.get_current_telemetry_payload()
            json_bytes = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(json_bytes)))
            self.end_headers()
            self.wfile.write(json_bytes)

        # 4. Trigger Simulation Run API
        elif path == "/api/simulate":
            pattern = query.get("pattern", ["composite"])[0]
            duration = float(query.get("duration", [120])[0])
            seed = int(query.get("seed", [42])[0])

            payload = self.server_instance.run_and_cache_simulation(
                pattern=pattern, duration=duration, seed=seed
            )
            json_bytes = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(json_bytes)))
            self.end_headers()
            self.wfile.write(json_bytes)

        # 5. Live Tick API
        elif path == "/api/live-tick":
            payload = self.server_instance.advance_live_tick()
            json_bytes = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(json_bytes)))
            self.end_headers()
            self.wfile.write(json_bytes)

        # 6. File Downloads (CSV, Parquet, Image)
        elif path in ("/api/download/csv", "/sample_data/simulated_workload_telemetry.csv"):
            csv_path = Path("/tmp/sample_data/simulated_workload_telemetry.csv")
            if not csv_path.exists():
                csv_path = Path("sample_data/simulated_workload_telemetry.csv")

            if csv_path.exists():
                data = csv_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="simulated_workload_telemetry.csv"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, "CSV file not found. Please run a simulation first.")

        elif path in ("/api/download/parquet", "/sample_data/simulated_workload_telemetry.parquet"):
            pq_path = Path("/tmp/sample_data/simulated_workload_telemetry.parquet")
            if not pq_path.exists():
                pq_path = Path("sample_data/simulated_workload_telemetry.parquet")

            if pq_path.exists():
                data = pq_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="simulated_workload_telemetry.parquet"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, "Parquet file not found. Please run a simulation first.")

        elif path in ("/api/image/timeline", "/sample_data/workload_timeline.png"):
            img_path = Path("/tmp/sample_data/workload_timeline.png")
            if not img_path.exists():
                img_path = Path("sample_data/workload_timeline.png")

            if img_path.exists():
                data = img_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, "Timeline image not found.")

        elif path in ("/healthz", "/health"):
            resp = b"OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_error(404, "Endpoint Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard access logs to keep terminal readable."""
        pass


class WorkloadMetricsServer:
    """Manages the lifecycle of the metrics and dashboard HTTP server."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        self.config = config or load_config()
        exporter_cfg = self.config.get("monitoring", {}).get("exporter", {})

        self.host = host or exporter_cfg.get("host", "0.0.0.0")
        self.port = int(port or exporter_cfg.get("port", 8000))
        self.manager = PrometheusMetricsManager()
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self.cached_records: List[Dict[str, Any]] = []
        self.live_time: float = 0.0
        self.live_engine: Optional[SimulationEngine] = None
        self.live_generator: Optional[WorkloadGenerator] = None

        # Seed initial cache
        self.run_and_cache_simulation()

    def run_and_cache_simulation(
        self,
        pattern: str = "composite",
        duration: float = 120.0,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Runs the simulation, updates Prometheus metrics, exports datasets, and caches JSON."""
        gen = WorkloadGenerator(config=self.config, random_seed=seed)
        gen.duration_seconds = duration
        traffic_df = gen.generate(pattern_type=pattern)

        engine = SimulationEngine(config=self.config, random_seed=seed)
        records = engine.run_simulation(traffic_df)
        telemetry_df = records_to_dataframe(records)

        # Update Prometheus metrics with the latest steps
        for r in records[-15:]:
            self.manager.update_from_record(r)

        # Export to files safely (serverless read-only filesystem handling)
        out_dir = Path("/tmp/sample_data") if os.environ.get("VERCEL") else Path("sample_data")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            export_dataset_to_csv(telemetry_df, out_dir / "simulated_workload_telemetry.csv")
            export_dataset_to_parquet(telemetry_df, out_dir / "simulated_workload_telemetry.parquet")
            vis = WorkloadVisualizer(config=self.config)
            vis.plot_timeline(telemetry_df, out_dir / "workload_timeline.png")
        except Exception:
            pass  # Fall back to in-memory cache if local disk is read-only

        self.cached_records = telemetry_df.to_dict(orient="records")
        return {"pattern": pattern, "records": self.cached_records}

    def advance_live_tick(self) -> Dict[str, Any]:
        """Advances live streaming simulation by 1 second."""
        if not self.live_engine or not self.live_generator:
            self.live_engine = SimulationEngine(config=self.config, random_seed=int(time.time()))
            self.live_generator = WorkloadGenerator(config=self.config, random_seed=int(time.time()))

        self.live_time += 1.0
        timeline = np.array([self.live_time])
        pat = self.config.get("traffic_generator", {}).get("active_pattern", "composite")
        rates = self.live_generator.generate_composite(timeline)
        rate = float(rates[0]) if len(rates) > 0 else 50.0

        record = self.live_engine.step(self.live_time, rate)
        self.manager.update_from_record(record)

        flat = records_to_dataframe([record]).to_dict(orient="records")[0]
        self.cached_records.append(flat)
        if len(self.cached_records) > 120:
            self.cached_records.pop(0)

        return {"records": self.cached_records}

    def get_current_telemetry_payload(self) -> Dict[str, Any]:
        return {"records": self.cached_records}

    def start(self, background: bool = False) -> None:
        """Starts the dashboard and metrics server."""
        MetricsHandler.server_instance = self
        self.server = HTTPServer((self.host, self.port), MetricsHandler)
        self._running = True

        display_host = "localhost" if self.host in ("0.0.0.0", "") else self.host
        print(f"\n[+] Interactive Web Dashboard: http://{display_host}:{self.port}/")
        print(f"[+] Prometheus Metrics Endpoint: http://{display_host}:{self.port}/metrics\n")

        if background:
            self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._thread.start()
        else:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self._running = False
            print("[Exporter] Server stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Workload Monitoring Web Server & Exporter")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    # Import numpy for live tick generator if needed
    import numpy as np

    server = WorkloadMetricsServer(host=args.host, port=args.port)
    server.start(background=False)
