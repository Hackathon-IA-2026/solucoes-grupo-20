import numpy as np

from motor_tarifa.customer.optimize import optimize_flexible_consumption


def test_optimization_preserves_energy_and_reduces_cost():
    consumption = np.ones(24)
    tariff = np.linspace(1.5, 0.5, 24)
    optimized, meta = optimize_flexible_consumption(consumption, tariff, flexible_fraction=0.25)
    assert np.isclose(optimized.sum(), consumption.sum())
    assert (optimized >= 0).all()
    assert float(np.dot(optimized, tariff)) < float(np.dot(consumption, tariff))
    assert meta['flexible_energy_kwh'] == 6.0
    assert meta['actually_shifted_kwh'] > 0


def test_zero_flexibility_keeps_curve_unchanged():
    consumption = np.arange(1, 25, dtype=float)
    tariff = np.ones(24)
    optimized, meta = optimize_flexible_consumption(consumption, tariff, flexible_fraction=0)
    assert np.allclose(optimized, consumption)
    assert meta['actually_shifted_kwh'] == 0
