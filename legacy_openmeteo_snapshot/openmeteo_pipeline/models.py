from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LocationConfig:
    """
    Localidade declarada em config/locations.json.
    """

    slug: str
    name: str
    state_code: str
    country_code: str
    active: bool


@dataclass(frozen=True)
class ResolvedLocation:
    """
    Localidade já associada a um resultado da
    Geocoding API do Open-Meteo.
    """

    slug: str
    requested_name: str
    requested_state_code: str
    requested_country_code: str

    geonames_id: int
    resolved_name: str
    country_code: str
    country_name: str | None

    state_name: str | None
    admin2_name: str | None

    latitude: float
    longitude: float
    elevation_meters: float | None
    timezone: str

    population: int | None
    feature_code: str | None

    source: str
    source_url: str
    resolved_at_utc: str
    raw_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyWeatherRecord:
    """
    Registro meteorológico normalizado por localidade
    e dia.

    Pode representar:
    - uma previsão;
    - um histórico recente provisório;
    - uma reanálise histórica.
    """

    daily_weather_id: str

    source: str
    source_service: str
    data_kind: str

    location_slug: str
    location_name: str
    state_code: str | None
    country_code: str

    latitude: float
    longitude: float
    timezone: str

    date_local: str

    weather_code: int | None

    temperature_2m_max: float | None
    temperature_2m_mean: float | None
    temperature_2m_min: float | None

    apparent_temperature_max: float | None
    apparent_temperature_mean: float | None
    apparent_temperature_min: float | None

    precipitation_sum: float | None
    rain_sum: float | None
    showers_sum: float | None
    snowfall_sum: float | None
    precipitation_hours: float | None
    precipitation_probability_max: float | None

    sunrise: str | None
    sunset: str | None
    daylight_duration: float | None
    sunshine_duration: float | None

    wind_speed_10m_max: float | None
    wind_gusts_10m_max: float | None
    wind_direction_10m_dominant: float | None

    source_grid_latitude: float | None
    source_grid_longitude: float | None
    source_elevation: float | None
    utc_offset_seconds: int | None

    units: dict[str, Any]

    raw_record_id: str
    raw_payload_hash: str
    raw_file: str
    retrieved_at_utc: str

    parser_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventCandidate:
    """
    Candidato a evento derivado de uma ou mais
    observações meteorológicas normalizadas.

    Um candidato ainda não representa um evento
    canônico confirmado. Ele preserva a regra,
    as métricas e os registros que motivaram sua
    geração.
    """

    candidate_id: str

    source: str
    source_service: str

    event_type: str
    event_family: str
    severity: str

    title: str
    summary: str

    start_at: str
    end_at: str
    timezone: str

    known_at: str
    status: str

    country_code: str
    state_code: str | None
    city_name: str
    location_slug: str

    latitude: float
    longitude: float

    metrics: dict[str, Any]
    rule: dict[str, Any]

    source_record_ids: list[str]
    source_payload_hashes: list[str]
    daily_weather_ids: list[str]

    keywords: list[str]

    detector_version: str
    rules_version: str

    extra_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalLocation:
    """
    Localidade associada a um evento canônico.

    O contrato permite que outros providers usem
    níveis territoriais diferentes. Para o
    Open-Meteo atual, o evento é associado à
    capital monitorada e sua abrangência canônica
    será definida separadamente no evento.
    """

    country_code: str
    state_code: str | None
    city_name: str | None
    location_slug: str | None

    latitude: float | None
    longitude: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalEvent:
    """
    Contrato compartilhado de evento canônico.

    Este objeto é independente do provider que
    originou o evento. Ele representa a forma que
    será consumida pelo calendário contextual e,
    posteriormente, pelas camadas de modelagem.

    A transformação de EventCandidate para este
    contrato é responsabilidade do canonical mapper.
    """

    id: str

    canonical_name: str
    summary: str

    event_type: str
    primary_category: str
    subcategory: str

    start_at_utc: str
    end_at_utc: str
    timezone_original: str
    known_at_utc: str

    status: str
    scope: str

    expected_intensity: str | None
    observed_intensity: str | None

    factual_confidence_score: float
    classification_confidence_score: float
    brazil_relevance_score: float

    locations: list[CanonicalLocation]

    sources: list[dict[str, Any]]
    evidence: dict[str, Any]

    created_at_utc: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
