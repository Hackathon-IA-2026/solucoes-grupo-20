import pytest

from motor_sin.climate.variables import convert_value


def test_wind_kmh_to_ms():
    assert convert_value("wind_speed_10m", 36.0, "km/h") == pytest.approx(10.0)


def test_fahrenheit_to_celsius():
    assert convert_value("temperature_2m", 68.0, "°F") == pytest.approx(20.0)


def test_unknown_unit_fails():
    with pytest.raises(ValueError):
        convert_value("solar_radiation", 1.0, "J/m²")
