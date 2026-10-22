"""Workload Generation Engine for simulating realistic distributed traffic patterns.

Supports:
- Steady baseline load with Gaussian/Poisson jitter
- Sudden spikes with configurable amplitude, duration, and decay
- Gradual trends (linear ramp up/down, sinusoidal diurnal waves)
- Stochastic noise models (Gaussian random walks, Ornstein-Uhlenbeck processes)
- Composite combinations of any patterns
- Deterministic reproducibility via explicit random seeding
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from interface.schema import TrafficPatternType


class WorkloadGenerator:
    """Configurable and reproducible synthetic workload traffic generator."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        random_seed: Optional[int] = None,
    ):
        self.config = config or {}
        sim_cfg = self.config.get("simulation", {})
        gen_cfg = self.config.get("traffic_generator", {})

        self.duration_seconds: float = float(sim_cfg.get("duration_seconds", 120.0))
        self.time_step_seconds: float = float(sim_cfg.get("time_step_seconds", 1.0))
        self.random_seed: Optional[int] = random_seed if random_seed is not None else sim_cfg.get("random_seed")
        self.gen_cfg: Dict[str, Any] = gen_cfg

        self._init_rng()

    def _init_rng(self) -> None:
        """Initializes the NumPy pseudo-random number generator for reproducibility."""
        self._stochastic_state: Optional[float] = None
        if self.random_seed is not None:
            self.rng = np.random.default_rng(self.random_seed)
        else:
            self.rng = np.random.default_rng()

    def set_seed(self, seed: int) -> None:
        """Updates random seed and reinitializes generator."""
        self.random_seed = seed
        self._init_rng()

    def generate_timeline(self) -> np.ndarray:
        """Generates the array of simulation timestamps."""
        return np.arange(0.0, self.duration_seconds, self.time_step_seconds, dtype=np.float64)

    def generate_steady(
        self,
        timeline: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Generates steady baseline traffic with controllable Gaussian jitter."""
        p = params or self.gen_cfg.get("steady", {})
        baseline: float = float(p.get("baseline_rps", 50.0))
        std_dev: float = float(p.get("jitter_std_dev", 5.0))
        min_rps: float = float(p.get("min_rps", 0.0))
        max_rps: float = float(p.get("max_rps", float("inf")))

        noise = self.rng.normal(loc=0.0, scale=std_dev, size=len(timeline))
        traffic = baseline + noise
        return np.clip(traffic, min_rps, max_rps)

    def generate_spike(
        self,
        timeline: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Generates baseline traffic with a sudden instantaneous demand surge."""
        p = params or self.gen_cfg.get("spike", {})
        baseline: float = float(p.get("baseline_rps", 40.0))
        amplitude: float = float(p.get("spike_amplitude_rps", 180.0))
        start_sec: float = float(p.get("spike_start_sec", 30.0))
        duration_sec: float = float(p.get("spike_duration_sec", 25.0))
        decay_rate: float = float(p.get("decay_rate", 0.15))

        traffic = np.full_like(timeline, baseline, dtype=np.float64)
        end_sec = start_sec + duration_sec

        for i, t in enumerate(timeline):
            if start_sec <= t < end_sec:
                # Active surge window
                traffic[i] = baseline + amplitude
            elif t >= end_sec:
                # Exponential decay back to baseline
                time_since_end = t - end_sec
                decayed_surge = amplitude * np.exp(-decay_rate * time_since_end)
                traffic[i] = baseline + decayed_surge

        # Add modest baseline jitter
        jitter = self.rng.normal(0.0, baseline * 0.05, size=len(timeline))
        return np.maximum(traffic + jitter, 0.0)

    def generate_gradual(
        self,
        timeline: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Generates gradual linear ramps or sinusoidal diurnal trends."""
        p = params or self.gen_cfg.get("gradual", {})
        baseline: float = float(p.get("baseline_rps", 30.0))
        peak: float = float(p.get("peak_rps", 120.0))
        trend_type: str = str(p.get("trend_type", "sinusoidal")).lower()

        if trend_type == "linear_ramp":
            midpoint = self.duration_seconds / 2.0
            ramp_up = np.interp(timeline, [0, midpoint], [baseline, peak])
            ramp_down = np.interp(timeline, [midpoint, self.duration_seconds], [peak, baseline])
            traffic = np.where(timeline <= midpoint, ramp_up, ramp_down)
        else:
            # Sinusoidal diurnal wave
            period = float(p.get("period_seconds", 60.0))
            phase = float(p.get("phase_shift_seconds", 0.0))
            amplitude = (peak - baseline) / 2.0
            mid_level = (peak + baseline) / 2.0
            traffic = mid_level + amplitude * np.sin((2 * np.pi * (timeline - phase)) / period)

        jitter = self.rng.normal(0.0, baseline * 0.04, size=len(timeline))
        return np.maximum(traffic + jitter, 0.0)

    def generate_noisy(
        self,
        timeline: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Generates stochastic noise models using Ornstein-Uhlenbeck random walk."""
        p = params or self.gen_cfg.get("noisy", {})
        baseline: float = float(p.get("baseline_rps", 45.0))
        volatility: float = float(p.get("volatility", 8.0))
        theta: float = float(p.get("mean_reversion_rate", 0.1))
        min_rps: float = float(p.get("min_rps", 5.0))
        max_rps: float = float(p.get("max_rps", 250.0))
        noise_type: str = str(p.get("noise_type", "gaussian_walk")).lower()
        dt = self.time_step_seconds
        traffic = np.zeros(len(timeline), dtype=np.float64)

        if len(timeline) == 1:
            prev_val = self._stochastic_state if self._stochastic_state is not None else baseline
            if noise_type == "poisson":
                cur_val = float(self.rng.poisson(lam=max(baseline, 1.0)))
            else:
                dx = theta * (baseline - prev_val) * dt + volatility * np.sqrt(dt) * self.rng.normal()
                cur_val = float(prev_val + dx)
            self._stochastic_state = float(np.clip(cur_val, min_rps, max_rps))
            traffic[0] = self._stochastic_state
            return traffic

        traffic[0] = self._stochastic_state if self._stochastic_state is not None else baseline
        for i in range(1, len(timeline)):
            if noise_type == "poisson":
                sample = self.rng.poisson(lam=max(baseline, 1.0))
                traffic[i] = sample
            else:
                dx = theta * (baseline - traffic[i - 1]) * dt + volatility * np.sqrt(dt) * self.rng.normal()
                traffic[i] = traffic[i - 1] + dx

        self._stochastic_state = float(traffic[-1])
        return np.clip(traffic, min_rps, max_rps)

    def generate_composite(
        self,
        timeline: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Generates rich composite traffic: diurnal base + periodic/stochastic surges + Brownian noise."""
        p = params or self.gen_cfg.get("composite", {})
        base_pattern = str(p.get("base_pattern", "gradual"))
        enable_spikes = bool(p.get("enable_spikes", True))
        enable_noise = bool(p.get("enable_noise", True))

        # Base pattern
        if base_pattern == "steady":
            base = self.generate_steady(timeline)
        else:
            base = self.generate_gradual(timeline)

        traffic = base.copy()

        # Add periodic or stochastic spikes with smooth exponential decay
        if enable_spikes:
            interval = float(p.get("spike_trigger_interval_sec", 45.0))
            spike_len = float(p.get("spike_length_sec", 15.0))
            multiplier = float(p.get("spike_magnitude_multiplier", 3.0))
            decay_rate = float(p.get("decay_rate", 0.15))

            for t_idx, t in enumerate(timeline):
                cycle_time = t % interval
                if cycle_time < spike_len:
                    traffic[t_idx] += base[t_idx] * (multiplier - 1.0)
                else:
                    decay = np.exp(-decay_rate * (cycle_time - spike_len))
                    traffic[t_idx] += base[t_idx] * (multiplier - 1.0) * decay

        # Add stochastic noise overlay
        if enable_noise:
            sigma = float(p.get("noise_sigma", 6.0))
            noise = self.rng.normal(0.0, sigma, size=len(timeline))
            traffic += noise

        return np.maximum(traffic, 0.0)

    def generate(
        self,
        pattern_type: Optional[TrafficPatternType | str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """High-level generator interface returning a timestamped DataFrame."""
        timeline = self.generate_timeline()
        selected_pattern = pattern_type or self.gen_cfg.get("active_pattern", "composite")
        pattern_str = selected_pattern.value if hasattr(selected_pattern, "value") else str(selected_pattern).lower()

        if pattern_str == TrafficPatternType.STEADY.value:
            rates = self.generate_steady(timeline, custom_params)
        elif pattern_str == TrafficPatternType.SPIKE.value:
            rates = self.generate_spike(timeline, custom_params)
        elif pattern_str == TrafficPatternType.GRADUAL.value:
            rates = self.generate_gradual(timeline, custom_params)
        elif pattern_str == TrafficPatternType.NOISY.value:
            rates = self.generate_noisy(timeline, custom_params)
        elif pattern_str == TrafficPatternType.COMPOSITE.value:
            rates = self.generate_composite(timeline, custom_params)
        else:
            raise ValueError(f"Unknown traffic pattern: {pattern_str}")

        return pd.DataFrame({
            "timestamp": timeline,
            "request_rate_rps": rates,
        })
