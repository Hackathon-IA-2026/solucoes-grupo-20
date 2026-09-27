from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize


def summarize_load_shift(original_kwh, shifted_kwh) -> dict:
    """Compare hourly energy profiles; kWh per one-hour interval equals mean kW."""
    original = np.asarray(original_kwh, dtype=float)
    shifted = np.asarray(shifted_kwh, dtype=float)
    if original.ndim != 1 or shifted.shape != original.shape or not len(original):
        raise ValueError('load profiles must be non-empty one-dimensional arrays with equal length')
    if not np.isfinite(original).all() or not np.isfinite(shifted).all() or (original < 0).any() or (shifted < 0).any():
        raise ValueError('load profiles must contain finite non-negative hourly energy')
    peak_before = float(original.max())
    peak_after = float(shifted.max())
    factor_before = float(original.mean()) / peak_before if peak_before else 0.0
    factor_after = float(shifted.mean()) / peak_after if peak_after else 0.0
    spread_before = float(original.std())
    spread_after = float(shifted.std())
    energy_preserved = bool(np.isclose(original.sum(), shifted.sum(), rtol=1e-9, atol=1e-9))
    return {
        'energy_before_kwh': float(original.sum()),
        'energy_after_kwh': float(shifted.sum()),
        'energy_preserved': energy_preserved,
        'peak_before_kw': peak_before,
        'peak_after_kw': peak_after,
        'peak_change_pct': 100 * (peak_after / peak_before - 1) if peak_before else 0.0,
        'load_factor_before_pct': 100 * factor_before,
        'load_factor_after_pct': 100 * factor_after,
        'load_factor_gain_pp': 100 * (factor_after - factor_before),
        'variability_reduction_pct': 100 * (1 - spread_after / spread_before) if spread_before else 0.0,
        'is_flatter': bool(energy_preserved and peak_after <= peak_before + 1e-9 and spread_after < spread_before - 1e-9),
    }


def optimize_flexible_consumption(
    consumption_kwh,
    dynamic_tariff_rs_kwh,
    *,
    flexible_fraction: float = 0.20,
    hourly_capacity_factor: float = 1.75,
    average_capacity_factor: float = 1.50,
    objective: str = 'cost',
) -> tuple[np.ndarray, dict]:
    """Shift flexible hourly energy for cost or constrained load smoothing.

    This is an explanatory demand-response scenario, not an appliance scheduler.
    The flatten objective minimizes variance without increasing the original
    peak or bill. Both objectives conserve energy and keep the inflexible load.
    """
    original = np.asarray(consumption_kwh, dtype=float)
    tariff = np.asarray(dynamic_tariff_rs_kwh, dtype=float)
    if original.ndim != 1 or tariff.ndim != 1 or len(original) != len(tariff) or len(original) == 0:
        raise ValueError('consumption and tariff must be non-empty one-dimensional arrays with equal length')
    if not np.isfinite(original).all() or not np.isfinite(tariff).all():
        raise ValueError('consumption and tariff must be finite')
    if (original < 0).any() or (tariff < 0).any():
        raise ValueError('consumption and tariff cannot be negative')
    if objective not in {'cost', 'flatten'}:
        raise ValueError('objective must be cost or flatten')
    if any(not np.isfinite(value) or value < 1 for value in (hourly_capacity_factor, average_capacity_factor)):
        raise ValueError('capacity factors must be finite and at least 1')
    fraction = float(flexible_fraction)
    if not 0.0 <= fraction <= 0.80:
        raise ValueError('flexible_fraction must be between 0 and 0.80')

    total = float(original.sum())
    if total <= 0 or fraction == 0:
        return original.copy(), {
            'objective': objective,
            'flexible_fraction': fraction,
            'flexible_energy_kwh': 0.0,
            'actually_shifted_kwh': 0.0,
        }

    fixed = original * (1.0 - fraction)
    optimized = fixed.copy()
    pool = total * fraction
    daily_average = total / len(original)
    capacity = np.maximum(original * float(hourly_capacity_factor), daily_average * float(average_capacity_factor))

    if objective == 'flatten':
        normalized = original / daily_average
        upper = np.minimum(capacity, original.max()) / daily_average
        lower = fixed / daily_average
        constraints = [LinearConstraint(np.ones(len(original)), len(original), len(original))]
        costs = tariff / tariff.max() if tariff.max() else tariff.copy()
        if np.ptp(costs) > 1e-12:
            constraints.append(LinearConstraint(costs, -np.inf, float(np.dot(normalized, costs))))
        solution = minimize(
            lambda values: 0.5 * float(np.square(values - 1).sum()),
            normalized,
            jac=lambda values: values - 1,
            method='SLSQP',
            bounds=Bounds(lower, upper),
            constraints=constraints,
            options={'ftol': 1e-12, 'maxiter': 200},
        )
        if not solution.success:
            raise ValueError(f'load smoothing failed: {solution.message}')
        optimized = solution.x * daily_average
        tolerance = 1e-8 * max(total, 1.0)
        if (
            abs(float(optimized.sum()) - total) > tolerance
            or (optimized < fixed - tolerance).any()
            or (optimized > upper * daily_average + tolerance).any()
            or float(np.dot(optimized - original, costs)) > tolerance
        ):
            raise ValueError('load smoothing did not satisfy energy, capacity or cost constraints')
        return optimized, {
            'objective': objective,
            'flexible_fraction': fraction,
            'flexible_energy_kwh': float(total * fraction),
            'actually_shifted_kwh': float(np.maximum(original - optimized, 0.0).sum()),
        }

    for idx in np.argsort(tariff, kind='stable'):
        if pool <= 1e-12:
            break
        headroom = max(0.0, float(capacity[idx] - optimized[idx]))
        take = min(pool, headroom)
        optimized[idx] += take
        pool -= take

    # The default capacity design guarantees enough aggregate headroom, but keep
    # a deterministic numerical fallback so energy conservation is exact.
    if pool > 1e-9:
        optimized[int(np.argmin(tariff))] += pool
        pool = 0.0

    correction = total - float(optimized.sum())
    optimized[int(np.argmin(tariff))] += correction
    actually_shifted = float(np.maximum(original - optimized, 0.0).sum())
    return optimized, {
        'objective': objective,
        'flexible_fraction': fraction,
        'flexible_energy_kwh': float(total * fraction),
        'actually_shifted_kwh': actually_shifted,
    }
