"""Predicta climate ingestion utilities.

Historical climate: ERA5-Land ARCO.
Operational forecast: remains outside this package (Open-Meteo/ECMWF forecast path).
"""

from .arco import ArcoClient, ArcoConfig, expected_hours_for_year

__all__ = ["ArcoClient", "ArcoConfig", "expected_hours_for_year"]
