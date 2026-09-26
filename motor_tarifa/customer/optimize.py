from __future__ import annotations

import numpy as np


def optimize_flexible_consumption(
    consumption_kwh,
    dynamic_tariff_rs_kwh,
    *,
    flexible_fraction: float = 0.20,
    hourly_capacity_factor: float = 1.75,
    average_capacity_factor: float = 1.50,
) -> tuple[np.ndarray, dict]:
    """Shift a configurable share of daily energy toward the cheapest hours.

    This is an explanatory demand-response scenario, not an appliance scheduler.
    Total energy is conserved. A per-hour headroom cap prevents the optimizer from
    unrealistically moving all flexible consumption into a single cheap hour.
    """
    original = np.asarray(consumption_kwh, dtype=float)
    tariff = np.asarray(dynamic_tariff_rs_kwh, dtype=float)
    if original.ndim != 1 or tariff.ndim != 1 or len(original) != len(tariff) or len(original) == 0:
        raise ValueError('consumption and tariff must be non-empty one-dimensional arrays with equal length')
    if np.isnan(original).any() or np.isnan(tariff).any():
        raise ValueError('consumption and tariff cannot contain NaN')
    if (original < 0).any() or (tariff < 0).any():
        raise ValueError('consumption and tariff cannot be negative')
    fraction = float(flexible_fraction)
    if not 0.0 <= fraction <= 0.80:
        raise ValueError('flexible_fraction must be between 0 and 0.80')

    total = float(original.sum())
    if total <= 0 or fraction == 0:
        return original.copy(), {
            'flexible_fraction': fraction,
            'flexible_energy_kwh': 0.0,
            'actually_shifted_kwh': 0.0,
        }

    fixed = original * (1.0 - fraction)
    optimized = fixed.copy()
    pool = total * fraction
    daily_average = total / len(original)
    capacity = np.maximum(original * float(hourly_capacity_factor), daily_average * float(average_capacity_factor))

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
        'flexible_fraction': fraction,
        'flexible_energy_kwh': float(total * fraction),
        'actually_shifted_kwh': actually_shifted,
    }
