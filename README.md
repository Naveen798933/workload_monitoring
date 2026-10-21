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
3. **External Configuration File:** [`config.yaml`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/config.yaml).

---

## 🚀 Quickstart Guide

### 1. Setup Virtual Environment & Install Dependencies
```bash
# Activate existing virtual environment
.\venv\Scripts\Activate.ps1

# Or install dependencies from requirements.txt
pip install -r requirements.txt
```

### 2. Run the Full End-to-End Pipeline
```bash
python run_demo.py
```
This executes:
- Traffic generation across all 5 pattern models.
- Discrete-event simulation with elastic worker pool and request queues.
- Export of telemetry datasets to CSV and Parquet formats.
- Bi-directional Pydantic schema validation.
- Generation of the 4-panel Matplotlib timeline visualization.
- Launch of the Prometheus exporter server and live metric scraping verification.

---

## 📊 Task Breakdown

### Task 1: Workload Simulator
- **Traffic Patterns:**
  - **Steady:** Baseline load with controllable Gaussian/Poisson variance.
  - **Spike:** Sudden surges with configurable amplitude, duration, and exponential decay.
  - **Gradual:** Diurnal sinusoidal waves or linear ramps.
  - **Noisy:** Mean-reverting stochastic processes (Ornstein-Uhlenbeck / Gaussian random walk).
  - **Composite:** Diurnal baseline overlaid with periodic bursts and stochastic jitter.
- **Reproducibility:** Seed-driven pseudo-random generator guarantees bit-for-bit identical traces across runs.
- **CLI Usage:**
  ```bash
  python simulator/run_simulation.py --config config.yaml --pattern composite --duration 120 --seed 42 --export-format both
  ```

### Task 2: Resource and Performance Model
- **Queue Subsystem ([`model/queue_system.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/model/queue_system.py)):**
  - FIFO and Priority Queues.
  - Drop Policies: `DROP_TAIL` (discard incoming), `DROP_HEAD` (evict oldest), `REJECT` (immediate refusal).
  - Automatic timeout purging of expired requests.
- **Worker Pool Cluster ([`model/worker_pool.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/model/worker_pool.py)):**
  - Worker lifecycle: `INITIALIZING` ➔ `WARMING_UP` ➔ `READY` ➔ `BUSY` ➔ `DRAINING` ➔ `STOPPED`.
  - Cold-start latency and graceful drain timeouts.
  - Dynamic auto-scaling based on CPU threshold and queue backlog.
- **Simulation Engine ([`model/engine.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/model/engine.py)):**
  - Concurrency penalty modeling.
  - Service latency distributions: Lognormal, Exponential, and Normal.
  - Accurate percentile computation ($p_{50}, p_{90}, p_{95}, p_{99}, \max, \min$).

### Task 3: Monitoring & Observability
- **Prometheus Collectors ([`monitoring/metrics.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/monitoring/metrics.py)):**
  - `workload_requests_total{status, endpoint}`: Throughput counter.
  - `workload_dropped_requests_total{reason}`: Drop counter.
  - `workload_active_workers{state}`: Gauge for worker lifecycle counts.
  - `workload_queue_depth` & `workload_queue_max_capacity`: Queue backpressure gauges.
  - `workload_cpu_utilization_ratio` & `workload_memory_used_bytes`: Resource utilization gauges.
  - `workload_request_duration_seconds`: Service latency histogram.
- **HTTP Exporter ([`monitoring/exporter_server.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/monitoring/exporter_server.py)):**
  - Run standalone exporter:
    ```bash
    python monitoring/exporter_server.py --port 8000 --live-feed --duration 60
    ```
- **Prometheus Scraping Setup:** Target configured in [`monitoring/prometheus.yml`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/monitoring/prometheus.yml).
- **Grafana Dashboard:** Declarative JSON schema in [`monitoring/grafana_dashboard.json`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/monitoring/grafana_dashboard.json) featuring:
  1. Real-time traffic throughput vs capacity.
  2. Latency distributions ($p_{50}/p_{95}/p_{99}$).
  3. Resource utilization (CPU % and Memory %).
  4. Queue backpressure and dropped request rates.
- **Fidelity Verification:**
  ```bash
  python monitoring/verify_metrics.py
  ```

### Task 4: Shared Data Interface
- **Pydantic Validation ([`interface/schema.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/interface/schema.py)):**
  - Physical unit enforcements (`MetricUnit`).
  - Monotonic percentile order ($p_{50} \le p_{90} \le p_{95} \le p_{99} \le \max$).
  - Strict resource bounds ($0.0 \le \text{CPU ratio} \le 1.0$, $\text{memory used} \le \text{memory total}$).
  - Monotonic timestamp sequences.
- **Data Dictionary:** Complete column definitions, ranges, and missing-value handling in [`interface/data_dictionary.md`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/interface/data_dictionary.md).
- **Tabular Serialization:** Bi-directional converters between Pydantic records, Pandas DataFrames, CSV, and Apache Parquet in [`interface/validator.py`](file:///c:/Users/K%20Yagnasri/OneDrive/Desktop/member%201%20_Workload%20monitoring/interface/validator.py).

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
