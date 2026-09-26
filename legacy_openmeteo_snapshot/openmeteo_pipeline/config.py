from __future__ import annotations

from pathlib import Path


# =============================================================================
# DIRETÓRIOS DO PROJETO
# =============================================================================

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent

CONFIG_DIR = BASE_DIR / "config"

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
EXPORT_DIR = DATA_DIR / "export"
SAMPLES_DIR = DATA_DIR / "samples"


# =============================================================================
# ARQUIVOS DE CONFIGURAÇÃO
# =============================================================================

LOCATIONS_CONFIG_PATH = (
    CONFIG_DIR
    / "locations.json"
)

EVENT_RULES_CONFIG_PATH = (
    CONFIG_DIR
    / "event_rules.json"
)


# =============================================================================
# DIRETÓRIOS DA GEOCODIFICAÇÃO
# =============================================================================

RAW_GEOCODING_DIR = (
    RAW_DIR
    / "geocoding"
)

SAMPLES_GEOCODING_DIR = (
    SAMPLES_DIR
    / "geocoding"
)

STAGING_LOCATIONS_PATH = (
    STAGING_DIR
    / "locations_resolved.json"
)


# =============================================================================
# OPEN-METEO
# =============================================================================

OPENMETEO_GEOCODING_URL = (
    "https://geocoding-api.open-meteo.com/"
    "v1/search"
)

REQUEST_TIMEOUT_SECONDS = 30

HTTP_429_MAX_RETRIES = 3

HTTP_429_FALLBACK_WAIT_SECONDS = 65

HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "ED-sazonalidade-openmeteo/0.1"
    ),
}

# =============================================================================
# PREVISÃO METEOROLÓGICA
# =============================================================================

OPENMETEO_FORECAST_URL = (
    "https://api.open-meteo.com/"
    "v1/forecast"
)

RAW_FORECAST_DIR = (
    RAW_DIR
    / "forecast"
)

FORECAST_MANIFEST_PATH = (
    STAGING_DIR
    / "forecast_collection_manifest.json"
)

FORECAST_DAYS = 15


# Variáveis agregadas por dia.
FORECAST_DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_mean",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_mean",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "showers_sum",
    "precipitation_hours",
    "precipitation_probability_max",
    "sunshine_duration",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
)


# =============================================================================
# CLIMA HISTÓRICO
# =============================================================================

OPENMETEO_HISTORICAL_URL = (
    "https://archive-api.open-meteo.com/"
    "v1/archive"
)

RAW_HISTORICAL_DIR = (
    RAW_DIR
    / "historical"
)

HISTORICAL_MANIFEST_PATH = (
    STAGING_DIR
    / "historical_collection_manifest.json"
)

HISTORICAL_DAYS = 15

# Os cinco dias históricos mais recentes são
# revisitados diariamente, mas ainda podem sofrer
# revisão da fonte. No staging eles são tratados
# como históricos provisórios.
HISTORICAL_PROVISIONAL_DAYS = 5

# D-15 até D-6.
HISTORICAL_REANALYSIS_DAYS = (
    HISTORICAL_DAYS
    - HISTORICAL_PROVISIONAL_DAYS
)


HISTORICAL_DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "sunshine_duration",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
)

# =============================================================================
# STAGING DIÁRIO NORMALIZADO
# =============================================================================

STAGING_DAILY_DIR = (
    STAGING_DIR
    / "daily"
)

STAGING_DAILY_CONSOLIDATED_PATH = (
    STAGING_DAILY_DIR
    / "openmeteo_daily_30d.json"
)

STAGING_DAILY_MANIFEST_PATH = (
    STAGING_DAILY_DIR
    / "openmeteo_daily_manifest.json"
)

DAILY_PARSER_VERSION = "1.1"

EXPECTED_DAILY_RECORDS_PER_LOCATION = (
    HISTORICAL_DAYS
    + FORECAST_DAYS
)

# =============================================================================
# LINHA DE BASE TÉRMICA
# =============================================================================

TEMPERATURE_BASELINE_VERSION = "1.1"

# A linha de base usa os dez anos completos
# imediatamente anteriores ao ano atual.
TEMPERATURE_BASELINE_YEARS = 10

# O modelo é explicitado para impedir que diferentes
# gerações de modelos sejam misturadas silenciosamente.
TEMPERATURE_BASELINE_MODEL = "era5_land"

TEMPERATURE_BASELINE_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
)

TEMPERATURE_BASELINE_PERCENTILES = (
    0.05,
    0.10,
    0.90,
    0.95,
)

# Em dez anos, cada mês terá aproximadamente
# 280 a 310 observações.
TEMPERATURE_BASELINE_MIN_SAMPLES_PER_MONTH = 250

RAW_TEMPERATURE_BASELINE_DIR = (
    RAW_HISTORICAL_DIR
    / "temperature_baseline"
)

STAGING_BASELINE_DIR = (
    STAGING_DIR
    / "baseline"
)

TEMPERATURE_BASELINE_CONSOLIDATED_PATH = (
    STAGING_BASELINE_DIR
    / "openmeteo_temperature_baseline.json"
)

TEMPERATURE_BASELINE_MANIFEST_PATH = (
    STAGING_BASELINE_DIR
    / "openmeteo_temperature_baseline_manifest.json"
)

# =============================================================================
# DETECÇÃO DE EVENTOS CLIMÁTICOS
# =============================================================================

STAGING_EVENTS_DIR = (
    STAGING_DIR
    / "events"
)

WEATHER_DETECTOR_VERSION = "1.2"

WEATHER_EVENT_CANDIDATES_PATH = (
    STAGING_EVENTS_DIR
    / "openmeteo_weather_event_candidates.json"
)

WEATHER_EVENT_CANDIDATES_MANIFEST_PATH = (
    STAGING_EVENTS_DIR
    / "openmeteo_weather_event_candidates_manifest.json"
)

WEATHER_EVENT_SUMMARY_JSON_PATH = (
    STAGING_EVENTS_DIR
    / "openmeteo_weather_event_summary.json"
)

WEATHER_EVENT_SUMMARY_CSV_PATH = (
    STAGING_EVENTS_DIR
    / "openmeteo_weather_event_summary.csv"
)

WEATHER_EVENT_SUMMARY_TXT_PATH = (
    STAGING_EVENTS_DIR
    / "openmeteo_weather_event_summary.txt"
)