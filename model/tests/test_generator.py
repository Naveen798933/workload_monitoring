"""Unit and Integration Tests for Workload Generator."""

import numpy as np
import pytest
from simulator.config import load_config
from simulator.generator import WorkloadGenerator
from interface.schema import TrafficPatternType


@pytest.fixture
def base_config():
    return load_config()


def test_reproducibility_with_seed(base_config):
    """Ensure identical random seed yields identical traffic timelines."""
    gen1 = WorkloadGenerator(config=base_config, random_seed=999)
    gen2 = WorkloadGenerator(config=base_config, random_seed=999)

    df1 = gen1.generate(pattern_type=TrafficPatternType.STEADY)
    df2 = gen2.generate(pattern_type=TrafficPatternType.STEADY)

    np.testing.assert_array_almost_equal(
        df1["request_rate_rps"].values,
        df2["request_rate_rps"].values,
        err_msg="Generators with identical seed must produce identical outputs",
    )


def test_different_seeds_produce_different_traces(base_config):
    """Ensure distinct seeds generate distinct stochastic paths."""
    gen1 = WorkloadGenerator(config=base_config, random_seed=101)
    gen2 = WorkloadGenerator(config=base_config, random_seed=202)

    df1 = gen1.generate(pattern_type=TrafficPatternType.NOISY)
    df2 = gen2.generate(pattern_type=TrafficPatternType.NOISY)

    assert not np.array_equal(df1["request_rate_rps"].values, df2["request_rate_rps"].values)


def test_steady_traffic_bounds(base_config):
    """Validate steady traffic baseline and variance boundaries."""
    baseline = 60.0
    jitter = 4.0
    gen = WorkloadGenerator(config=base_config, random_seed=42)
    df = gen.generate(
        pattern_type=TrafficPatternType.STEADY,
        custom_params={"baseline_rps": baseline, "jitter_std_dev": jitter, "min_rps": 10.0, "max_rps": 100.0},
    )

    rates = df["request_rate_rps"].values
    assert len(rates) > 0
    assert abs(np.mean(rates) - baseline) < (jitter * 1.5)
    assert np.all(rates >= 10.0)
    assert np.all(rates <= 100.0)


def test_spike_traffic_amplitude_and_decay(base_config):
    """Validate instantaneous surge and exponential decay."""
    gen = WorkloadGenerator(config=base_config, random_seed=42)
    df = gen.generate(
        pattern_type=TrafficPatternType.SPIKE,
        custom_params={
            "baseline_rps": 30.0,
            "spike_amplitude_rps": 150.0,
            "spike_start_sec": 10.0,
            "spike_duration_sec": 15.0,
            "decay_rate": 0.2,
        },
    )

    t = df["timestamp"].values
    rates = df["request_rate_rps"].values

    # Pre-spike period
    pre_spike = rates[t < 10.0]
    assert np.mean(pre_spike) < 45.0

    # Surge period: ~180 RPS
    surge = rates[(t >= 10.0) & (t < 25.0)]
    assert np.min(surge) >= 170.0

    # Post-spike decay: should decline
    post_spike_early = rates[(t >= 25.0) & (t < 30.0)]
    post_spike_late = rates[t >= 50.0]
    assert np.mean(post_spike_early) > np.mean(post_spike_late)


def test_gradual_diurnal_pattern(base_config):
    """Validate sinusoidal diurnal pattern oscillates between baseline and peak."""
    gen = WorkloadGenerator(config=base_config, random_seed=42)
    df = gen.generate(
        pattern_type=TrafficPatternType.GRADUAL,
        custom_params={
            "baseline_rps": 20.0,
            "peak_rps": 80.0,
            "trend_type": "sinusoidal",
            "period_seconds": 40.0,
            "phase_shift_seconds": 0.0,
        },
    )

    rates = df["request_rate_rps"].values
    assert np.min(rates) >= 15.0
    assert np.max(rates) <= 85.0
    assert np.mean(rates) == pytest.approx(50.0, abs=5.0)
