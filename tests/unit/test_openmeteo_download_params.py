import pytest

from motor_sin.climate.openmeteo import build_archive_parameters


def test_archive_parameters_freeze_era5_land_and_utc():
    params = build_archive_parameters(
        latitude=-22.9,
        longitude=-43.2,
        start_date="2025-01-01",
        end_date="2025-01-02",
    )
    assert params["models"] == "era5_land"
    assert params["timezone"] == "GMT"
    assert "temperature_2m" in params["hourly"]
    assert "shortwave_radiation" in params["hourly"]


def test_archive_parameters_reject_inverted_period():
    with pytest.raises(ValueError):
        build_archive_parameters(
            latitude=0,
            longitude=0,
            start_date="2025-01-02",
            end_date="2025-01-01",
        )


def test_archive_parameters_allow_era5_seamless_for_e2():
    params = build_archive_parameters(
        latitude=-23.55, longitude=-46.63,
        start_date='2025-01-01', end_date='2025-01-02',
        model='era5_seamless',
    )
    assert params['models'] == 'era5_seamless'
    assert 'precipitation' in params['hourly']
    assert 'wind_speed_10m' in params['hourly']
    assert 'shortwave_radiation' in params['hourly']
