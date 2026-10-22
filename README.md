# Member 1 — Workload Simulation and Monitoring

A production-grade, modular, and **fully dynamic (zero hardcoded constants)** distributed systems workload generation, queuing performance modeling, and Prometheus/Grafana observability engine.

---

## 🏗️ Architecture & Component Layout

```
member 1 _Workload monitoring/
├── config.yaml                    # Centralized dynamic configuration (zero magic numbers)
├── requirements.txt               # Pinned production dependencies
├── pytest.ini                     # Pytest runner configuration
├── run_demo.py                    # Complete end-to-end execution script
│
├── simulator/                     # Task 1: Dynamic Workload Generation Engine
│   ├── __init__.py
│   ├── config.py                  # Dynamic configuration loader & env var overrides
│   ├── generator.py               # Traffic generator (steady, spike, gradual, noisy, composite)
│   ├── visualizer.py              # Zero-hardcoding Matplotlib timeline renderer
│   └── run_simulation.py          # Standalone CLI execution entry point
│
├── model/                         # Task 2: Resource and Performance Model
│   ├── __init__.py
│   ├── queue_system.py            # FIFO / Priority queues, timeout purging, drop policies
│   ├── worker_pool.py             # Stateful worker lifecycles, cold-start latency, auto-scaling
│   ├── engine.py                  # Discrete-event performance simulation engine
│   └── tests/                     # Task 2 & Overload Test Suite
│       ├── test_generator.py      # Reproducibility, pattern bounds, and seed tests
│       ├── test_model.py          # Worker lifecycle, queues, and auto-scaling tests
│       └── test_overload.py       # Stress testing, queue saturation, and drop behavior tests
│
├── monitoring/                    # Task 3: Prometheus Instrumentation & Observability
│   ├── __init__.py
│   ├── metrics.py                 # Prometheus Counters, Gauges, and Histograms manager
│   ├── exporter_server.py         # HTTP metrics server exposing /metrics
│   ├── prometheus.yml             # Parameterized Prometheus scrape configuration
│   ├── grafana_dashboard.json     # Declarative 4-panel Grafana dashboard definition
│   └── verify_metrics.py          # Fidelity validator (scraped metrics vs simulator state)
│
├── interface/                     # Task 4: Shared Data Interface & Contracts
│   ├── __init__.py
│   ├── schema.py                  # Strict Pydantic models, units, and validation rules
│   ├── validator.py               # DataFrame / CSV / Parquet serialization pipeline
│   ├── data_dictionary.md         # Detailed field-by-field schema documentation
│   └── tests/
│       └── test_interface.py      # Automated schema rejection and contract tests
│
└── sample_data/                   # Exported Artifacts
    ├── simulated_workload_telemetry.csv
    ├── simulated_workload_telemetry.parquet
    └── workload_timeline.png
```

---

## 🎯 Architectural Mandate: Zero Hardcoding

Every operational parameter is decoupled from logic files and resolved via a strict configuration hierarchy:
1. **Programmatic Parameter Injection:** Dynamic keyword arguments passed directly to functions.
2. **Environment Variable Overrides:**
   - `WORKLOAD_CONFIG_PATH`: Path to custom YAML configuration file.
   - `SIM_DURATION_SEC`: Overrides simulation duration.
   - `SIM_SEED`: Overrides random generator seed for deterministic tests.
   - `SIM_EXPORT_FORMAT`: `csv`, `parquet`, or `both`.
   - `TRAFFIC_PATTERN`: `steady`, `spike`, `gradual`, `noisy`, or `composite`.
   - `METRICS_PORT`: Bind port for Prometheus HTTP exporter (default: `8000`).
3. **External Configuration File:** [`config.yaml`](config.yaml).

---

## 🚀 Quickstart Guide

### 1. Setup Virtual Environment & Install Dependencies
```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Install production dependencies
pip install -r requirements.txt
```

### 2. Run the Real-Time Web Dashboard & Prometheus Exporter
```bash
python web_server.py 8000
```
- **Real-Time Interactive Dashboard:** [http://localhost:8000/](http://localhost:8000/)
- **Live SSE Telemetry Stream:** [http://localhost:8000/api/v1/stream](http://localhost:8000/api/v1/stream)
- **Live Workload Ingestion:** `POST http://localhost:8000/api/v1/workload/ingest`
- **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)

### 3. Run the Full End-to-End Test Suite
```bash
python run_demo.py
```

---

## 📊 Task Breakdown

### Task 1: Workload Simulator & Generator
- **Traffic Patterns:**
  - **Steady:** Baseline load with controllable Gaussian/Poisson variance.
  - **Spike:** Sudden surges with configurable amplitude, duration, and exponential decay.
  - **Gradual:** Diurnal sinusoidal waves or linear ramps.
  - **Noisy:** Mean-reverting stochastic processes (Ornstein-Uhlenbeck / Gaussian random walk).
  - **Composite:** Diurnal baseline overlaid with periodic bursts and smooth decay.
- **CLI Usage:**
  ```bash
  python simulator/run_simulation.py --config config.yaml --pattern composite --duration 120 --seed 42 --export-format both
  ```

### Task 2: Resource and Performance Model
- **Queue Subsystem ([`model/queue_system.py`](model/queue_system.py)):**
  - Thread-safe FIFO and Priority Queues with `threading.RLock()`.
  - Drop Policies: `DROP_TAIL` (discard incoming), `DROP_HEAD` (evict lowest priority), `REJECT` (immediate 503).
  - Automatic timeout purging of expired requests.
- **Worker Pool Cluster ([`model/worker_pool.py`](model/worker_pool.py)):**
  - Worker lifecycle: `INITIALIZING` ➔ `WARMING_UP` ➔ `READY` ➔ `BUSY` ➔ `DRAINING` ➔ `STOPPED`.
  - Cold-start latency and graceful drain timeouts.
  - Dynamic auto-scaling based on true capacity-ratio CPU threshold and queue backlog.
- **Simulation Engine ([`model/engine.py`](model/engine.py)):**
  - Exact request remainder distribution across workers.
  - Latency distributions: Lognormal, Exponential, and Normal with monotonic percentile guarantees.

### Task 3: Monitoring & Observability
- **Prometheus Collectors ([`monitoring/metrics.py`](monitoring/metrics.py)):**
  - `workload_requests_total{status, endpoint}`: Throughput counter.
  - `workload_dropped_requests_total{reason}`: Drop counter.
  - `workload_latency_p50_seconds`, `workload_latency_p95_seconds`, `workload_latency_p99_seconds`: Dedicated quantile gauges.
  - `workload_active_workers{state}`: Gauge for worker lifecycle counts.
  - `workload_queue_depth` & `workload_queue_max_capacity`: Queue backpressure gauges.
  - `workload_cpu_utilization_ratio` & `workload_memory_used_bytes`: Resource utilization gauges.
- **HTTP Exporter & Streamer ([`monitoring/exporter_server.py`](monitoring/exporter_server.py)):**
  - Multi-threaded `ThreadingHTTPServer` with Server-Sent Events (`/api/v1/stream`) and real workload ingestion (`/api/v1/workload/ingest`).
- **Prometheus Scraping Setup:** Target configured in [`monitoring/prometheus.yml`](monitoring/prometheus.yml).
- **Grafana Dashboard:** Declarative JSON schema in [`monitoring/grafana_dashboard.json`](monitoring/grafana_dashboard.json).
- **Fidelity Verification:**
  ```bash
  python monitoring/verify_metrics.py
  ```

### Task 4: Shared Data Interface
- **Pydantic Validation ([`interface/schema.py`](interface/schema.py)):**
  - Physical unit enforcements (`MetricUnit`).
  - Monotonic percentile order ($p_{50} \le p_{90} \le p_{95} \le p_{99} \le \max$).
  - Strict resource bounds ($0.0 \le \text{CPU ratio} \le 1.0$, $\text{memory used} \le \text{memory total}$).
  - Timezone-aware UTC timestamp sequences.
- **Data Dictionary:** Complete column definitions, ranges, and missing-value handling in [`interface/data_dictionary.md`](interface/data_dictionary.md).
- **Tabular Serialization:** Bi-directional converters between Pydantic records, Pandas DataFrames, CSV, and Apache Parquet in [`interface/validator.py`](interface/validator.py).

---

## 🧪 Automated Test Suite

Run the full automated test suite with pytest:
```bash
pytest
```

### Test Coverage Highlights:
- **`model/tests/test_generator.py`**:
  - Deterministic reproducibility under identical seeds.
  - Variance divergence under distinct seeds.
  - Boundary compliance for Steady, Spike, and Gradual diurnal curves.
- **`model/tests/test_model.py`**:
  - FIFO and Priority queue dispatch orders.
  - Worker cold-start delay and warm-up state transitions.
  - Graceful worker drain before stopping.
  - Elastic auto-scaling under simulated CPU and queue pressure.
- **`model/tests/test_overload.py`**:
  - `DROP_TAIL` refusal on backlog overflow.
  - `DROP_HEAD` oldest-request eviction.
  - Timeout deadline expiration purging.
  - Telemetry error and drop rate accounting under 500 RPS overload.
- **`interface/tests/test_interface.py`**:
  - Rejection of inverted percentiles ($p_{95} < p_{50}$).
  - Rejection of negative latencies.
  - Rejection of CPU utilization $> 1.0$.
  - Rejection of memory usage exceeding cluster allocation.
  - Bi-directional DataFrame serialization fidelity.
