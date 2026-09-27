import numpy as np
import pytest

from motor_tarifa.customer.optimize import optimize_flexible_consumption, summarize_load_shift


def test_optimization_preserves_energy_and_reduces_cost():
    consumption = np.ones(24)
    tariff = np.linspace(1.5, 0.5, 24)
    optimized, meta = optimize_flexible_consumption(consumption, tariff, flexible_fraction=0.25)
    assert np.isclose(optimized.sum(), consumption.sum())
    assert (optimized >= 0).all()
    assert float(np.dot(optimized, tariff)) < float(np.dot(consumption, tariff))
    assert meta['flexible_energy_kwh'] == 6.0
    assert meta['actually_shifted_kwh'] > 0


@pytest.mark.parametrize('objective', ['cost', 'flatten'])
def test_zero_flexibility_keeps_curve_unchanged(objective):
    consumption = np.arange(1, 25, dtype=float)
    tariff = np.ones(24)
    optimized, meta = optimize_flexible_consumption(consumption, tariff, flexible_fraction=0, objective=objective)
    assert np.allclose(optimized, consumption)
    assert meta['actually_shifted_kwh'] == 0


def test_smoothing_reduces_peak_and_variability_without_increasing_cost():
    consumption = np.array([4.] * 4 + [1.] * 20)
    tariff = np.array([1.4] * 4 + [.5] * 20)
    shifted, meta = optimize_flexible_consumption(consumption, tariff, flexible_fraction=.25, objective='flatten')
    np.testing.assert_allclose(shifted, [3.] * 4 + [1.2] * 20, atol=1e-8)
    assert float(np.dot(shifted, tariff)) <= float(np.dot(consumption, tariff))
    assert (shifted >= consumption * .75 - 1e-9).all()
    assert meta['actually_shifted_kwh'] == pytest.approx(4.)
    metrics = summarize_load_shift(consumption, shifted)
    assert metrics['energy_preserved']
    assert metrics['energy_before_kwh'] == pytest.approx(36.)
    assert metrics['energy_after_kwh'] == pytest.approx(36.)
    assert metrics['peak_change_pct'] == pytest.approx(-25.)
    assert metrics['load_factor_before_pct'] == pytest.approx(37.5)
    assert metrics['load_factor_after_pct'] == pytest.approx(50.)
    assert metrics['is_flatter']


def test_smoothing_does_not_create_a_synchronized_cheap_hour_peak():
    consumption = np.ones(24)
    tariff = np.linspace(1.5, .5, 24)
    cheapest, _ = optimize_flexible_consumption(consumption, tariff)
    shifted, _ = optimize_flexible_consumption(consumption, tariff, objective='flatten')
    assert cheapest.max() > consumption.max()
    np.testing.assert_allclose(shifted, consumption)
    assert not summarize_load_shift(consumption, cheapest)['is_flatter']


def test_smoothing_reports_no_improvement_when_cost_blocks_the_shift():
    consumption = np.array([4.] * 4 + [1.] * 20)
    tariff = np.array([.1] * 4 + [1.] * 20)
    shifted, _ = optimize_flexible_consumption(consumption, tariff, objective='flatten')
    np.testing.assert_allclose(shifted, consumption, atol=1e-8)
    assert not summarize_load_shift(consumption, shifted)['is_flatter']


@pytest.mark.parametrize('invalid', [np.nan, np.inf, -1.])
def test_smoothing_rejects_invalid_energy(invalid):
    with pytest.raises(ValueError):
        optimize_flexible_consumption([invalid, 1.], [1., 1.], objective='flatten')


def test_empty_demand_has_finite_metrics():
    shifted, _ = optimize_flexible_consumption(np.zeros(24), np.ones(24), objective='flatten')
    metrics = summarize_load_shift(np.zeros(24), shifted)
    assert metrics['energy_preserved']
    assert metrics['load_factor_after_pct'] == 0
    assert not metrics['is_flatter']
