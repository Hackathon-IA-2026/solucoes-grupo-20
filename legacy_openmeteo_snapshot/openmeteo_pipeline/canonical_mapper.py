from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openmeteo_pipeline.models import (
    CanonicalLocation,
    EventCandidate,
)


# =============================================================================
# CONTRATO SEMÂNTICO OPEN-METEO -> CANÔNICO
# =============================================================================

CANONICAL_EVENT_TYPE = "derived"
CANONICAL_PRIMARY_CATEGORY = "climaticos"
CANONICAL_SCOPE = "municipal"


SUBCATEGORY_BY_EVENT_TYPE = {
    "unusually_hot_day": "unusual_heat",
    "extreme_heat_day": "extreme_heat",
    "heat_wave_candidate": "heat_wave",
    "unusually_cold_day": "unusual_cold",
    "extreme_cold_day": "extreme_cold",
    "cold_wave_candidate": "cold_wave",
    "heavy_rain_day": "heavy_rain",
    "extreme_rain_day": "extreme_rain",
    "strong_wind_day": "strong_wind",
    "severe_wind_day": "severe_wind",
    "extreme_wind_day": "extreme_wind",
    "storm_candidate": "storm",
}


CANONICAL_STATUSES = {
    "confirmed",
    "provisional",
    "forecast",
    "ongoing",
}


CANONICAL_INTENSITIES = {
    "moderate",
    "severe",
    "extreme",
}


# =============================================================================
# VALIDAÇÃO DO CANDIDATO
# =============================================================================

def validar_candidato_openmeteo(
    candidato: EventCandidate,
) -> None:
    """
    Valida os campos mínimos necessários para
    transformar um EventCandidate do Open-Meteo
    em representação canônica.

    Esta validação não verifica scores ou identidade
    canônica, que pertencem às etapas posteriores.
    """
    if candidato.source != "open-meteo":
        raise ValueError(
            "O canonical mapper do Open-Meteo recebeu "
            f"source={candidato.source!r}."
        )

    if candidato.source_service != "weather_detector":
        raise ValueError(
            "O candidato não foi produzido pelo "
            "weather_detector: "
            f"{candidato.source_service!r}."
        )

    if candidato.event_type not in SUBCATEGORY_BY_EVENT_TYPE:
        raise ValueError(
            "Tipo de evento climático sem mapeamento "
            "canônico: "
            f"{candidato.event_type!r}."
        )

    if candidato.severity not in CANONICAL_INTENSITIES:
        raise ValueError(
            "Severidade do candidato não possui "
            "equivalente canônico: "
            f"{candidato.severity!r}."
        )

    if not candidato.location_slug:
        raise ValueError(
            "Candidato climático sem location_slug."
        )

    if not candidato.city_name:
        raise ValueError(
            "Candidato climático sem city_name."
        )

    if not candidato.country_code:
        raise ValueError(
            "Candidato climático sem country_code."
        )

    if not candidato.timezone:
        raise ValueError(
            "Candidato climático sem timezone."
        )

    if not candidato.start_at:
        raise ValueError(
            "Candidato climático sem start_at."
        )

    if not candidato.end_at:
        raise ValueError(
            "Candidato climático sem end_at."
        )

    if not candidato.known_at:
        raise ValueError(
            "Candidato climático sem known_at."
        )


# =============================================================================
# DATAS
# =============================================================================

def parsear_datetime_com_timezone(
    valor: str,
) -> datetime:
    """
    Converte um timestamp ISO 8601 em datetime
    timezone-aware.

    O sufixo Z é convertido explicitamente para UTC.
    Timestamps sem timezone são rejeitados para evitar
    conversões silenciosamente incorretas.
    """
    texto = valor.strip()

    if texto.endswith("Z"):
        texto = (
            texto[:-1]
            + "+00:00"
        )

    data_hora = datetime.fromisoformat(
        texto
    )

    if data_hora.tzinfo is None:
        raise ValueError(
            "Timestamp sem timezone não pode ser "
            f"convertido para UTC: {valor!r}."
        )

    return data_hora


def converter_datetime_para_utc(
    valor: str,
) -> str:
    """
    Converte um timestamp ISO 8601 timezone-aware
    para UTC preservando o instante real.
    """
    data_hora = (
        parsear_datetime_com_timezone(
            valor
        )
    )

    data_hora_utc = (
        data_hora.astimezone(
            timezone.utc
        )
    )

    return data_hora_utc.isoformat()


# =============================================================================
# CATEGORIZAÇÃO
# =============================================================================

def mapear_subcategoria(
    event_type: str,
) -> str:
    """
    Converte o event_type interno do detector em
    subcategoria canônica.
    """
    subcategoria = (
        SUBCATEGORY_BY_EVENT_TYPE.get(
            event_type
        )
    )

    if subcategoria is None:
        raise ValueError(
            "Tipo de evento sem subcategoria canônica: "
            f"{event_type!r}."
        )

    return subcategoria


def construir_nome_canonico(
    candidato: EventCandidate,
) -> str:
    """
    Constrói o nome canônico do evento.

    O nome preserva a semântica do título produzido
    pelo detector, mas remove dependência futura de
    textos de apresentação do relatório.
    """
    subcategoria = mapear_subcategoria(
        candidato.event_type
    )

    nomes = {
        "unusual_heat": (
            f"Calor excepcional em {candidato.city_name}"
        ),
        "extreme_heat": (
            f"Calor extremo em {candidato.city_name}"
        ),
        "heat_wave": (
            f"Onda de calor em {candidato.city_name}"
        ),
        "unusual_cold": (
            f"Frio excepcional em {candidato.city_name}"
        ),
        "extreme_cold": (
            f"Frio extremo em {candidato.city_name}"
        ),
        "cold_wave": (
            f"Onda de frio em {candidato.city_name}"
        ),
        "heavy_rain": (
            f"Chuva intensa em {candidato.city_name}"
        ),
        "extreme_rain": (
            f"Chuva extrema em {candidato.city_name}"
        ),
        "strong_wind": (
            f"Vento forte em {candidato.city_name}"
        ),
        "severe_wind": (
            f"Ventania severa em {candidato.city_name}"
        ),
        "extreme_wind": (
            f"Ventania extrema em {candidato.city_name}"
        ),
        "storm": (
            f"Tempestade em {candidato.city_name}"
        ),
    }

    return nomes[
        subcategoria
    ]


# =============================================================================
# STATUS CANÔNICO
# =============================================================================

def extrair_data_kinds(
    candidato: EventCandidate,
) -> set[str]:
    """
    Obtém os data_kinds que realmente compõem o
    candidato.

    O detector registra essa informação em
    extra_data.data_kinds. Há um fallback controlado
    para candidatos gerados antes dessa informação.
    """
    data_kinds_raw = (
        candidato.extra_data.get(
            "data_kinds"
        )
    )

    if isinstance(
        data_kinds_raw,
        list,
    ):
        resultado = {
            str(item)
            for item in data_kinds_raw
            if item is not None
        }

        if resultado:
            return resultado

    fallback = {
        "forecast": {
            "forecast",
        },
        "provisional": {
            "historical_provisional",
        },
        "historical_reanalysis": {
            "historical_reanalysis",
        },
    }

    resultado_fallback = fallback.get(
        candidato.status
    )

    if resultado_fallback is not None:
        return set(
            resultado_fallback
        )

    raise ValueError(
        "Não foi possível determinar os data_kinds "
        "do candidato. candidate_id="
        f"{candidato.candidate_id!r}, "
        f"status={candidato.status!r}."
    )


def mapear_status_canonico(
    candidato: EventCandidate,
) -> str:
    """
    Normaliza a natureza temporal do candidato.

    Regras:

    - somente reanálise:
      confirmed;

    - existe histórico provisório, sem forecast:
      provisional;

    - somente forecast:
      forecast;

    - existe forecast junto de qualquer informação
      passada:
      ongoing.

    O status interno mixed nunca é exportado.
    """
    data_kinds = extrair_data_kinds(
        candidato
    )

    permitidos = {
        "historical_reanalysis",
        "historical_provisional",
        "forecast",
    }

    desconhecidos = (
        data_kinds
        - permitidos
    )

    if desconhecidos:
        raise ValueError(
            "data_kinds não reconhecidos no candidato "
            f"{candidato.candidate_id}: "
            f"{sorted(desconhecidos)}."
        )

    tem_forecast = (
        "forecast"
        in data_kinds
    )

    tem_passado = bool(
        data_kinds
        & {
            "historical_reanalysis",
            "historical_provisional",
        }
    )

    if (
        tem_forecast
        and tem_passado
    ):
        return "ongoing"

    if data_kinds == {
        "forecast",
    }:
        return "forecast"

    if (
        "historical_provisional"
        in data_kinds
    ):
        return "provisional"

    if data_kinds == {
        "historical_reanalysis",
    }:
        return "confirmed"

    raise ValueError(
        "Combinação temporal não suportada para "
        f"{candidato.candidate_id}: "
        f"{sorted(data_kinds)}."
    )


# =============================================================================
# INTENSIDADE ESPERADA E OBSERVADA
# =============================================================================

def mapear_intensidades_canonicas(
    candidato: EventCandidate,
    status_canonico: str,
) -> tuple[str | None, str | None]:
    """
    Separa intensidade esperada de intensidade
    observada de acordo com a natureza temporal
    do evento.

    Retorno:
    1. expected_intensity;
    2. observed_intensity.

    Regras:
    - forecast:
      intensidade apenas esperada;

    - confirmed:
      intensidade apenas observada;

    - provisional:
      intensidade observada, porém ainda sujeita
      a revisão da camada histórica;

    - ongoing:
      há evidência passada e continuação prevista,
      portanto a intensidade é representada nos
      dois lados.
    """
    intensidade = str(
        candidato.severity
    )

    if intensidade not in CANONICAL_INTENSITIES:
        raise ValueError(
            "Intensidade canônica inválida: "
            f"{intensidade!r}."
        )

    if status_canonico == "forecast":
        return (
            intensidade,
            None,
        )

    if status_canonico == "confirmed":
        return (
            None,
            intensidade,
        )

    if status_canonico == "provisional":
        return (
            None,
            intensidade,
        )

    if status_canonico == "ongoing":
        return (
            intensidade,
            intensidade,
        )

    raise ValueError(
        "Status canônico sem regra de intensidade: "
        f"{status_canonico!r}."
    )


# =============================================================================
# LOCALIZAÇÃO
# =============================================================================

def construir_localizacao_canonica(
    candidato: EventCandidate,
) -> CanonicalLocation:
    """
    Constrói a localização canônica do candidato.

    O Open-Meteo atual trabalha por capital monitorada,
    portanto o escopo será municipal na camada canônica.
    """
    return CanonicalLocation(
        country_code=(
            candidato.country_code
        ),
        state_code=(
            candidato.state_code
        ),
        city_name=(
            candidato.city_name
        ),
        location_slug=(
            candidato.location_slug
        ),
        latitude=float(
            candidato.latitude
        ),
        longitude=float(
            candidato.longitude
        ),
    )


# =============================================================================
# PROVENIÊNCIA
# =============================================================================

def construir_sources_base(
    candidato: EventCandidate,
) -> list[dict[str, Any]]:
    """
    Preserva a proveniência mínima necessária para
    rastrear o evento canônico até o provider.
    """
    return [
        {
            "source": candidato.source,
            "source_service": (
                candidato.source_service
            ),
            "candidate_id": (
                candidato.candidate_id
            ),
            "source_record_ids": list(
                candidato.source_record_ids
            ),
            "source_payload_hashes": list(
                candidato.source_payload_hashes
            ),
            "daily_weather_ids": list(
                candidato.daily_weather_ids
            ),
        }
    ]


def construir_evidence_base(
    candidato: EventCandidate,
) -> dict[str, Any]:
    """
    Mantém os elementos necessários para explicar
    por que o detector criou o candidato.
    """
    return {
        "provider_event_type": (
            candidato.event_type
        ),
        "event_family": (
            candidato.event_family
        ),
        "provider_severity": (
            candidato.severity
        ),
        "provider_status": (
            candidato.status
        ),
        "data_kinds": sorted(
            extrair_data_kinds(
                candidato
            )
        ),
        "metrics": dict(
            candidato.metrics
        ),
        "rule": dict(
            candidato.rule
        ),
        "keywords": list(
            candidato.keywords
        ),
        "detector_version": (
            candidato.detector_version
        ),
        "rules_version": (
            candidato.rules_version
        ),
        "detector_extra_data": dict(
            candidato.extra_data
        ),
    }


# =============================================================================
# MAPEAMENTO BASE
# =============================================================================

def mapear_candidato_base(
    candidato: EventCandidate,
) -> dict[str, Any]:
    """
    Produz a parte do contrato canônico que já pode
    ser definida nesta etapa.

    Inclui:
    - categoria e subcategoria;
    - datas UTC;
    - status canônico;
    - intensidade esperada/observada;
    - localização;
    - proveniência;
    - evidências.

    Ainda não inclui:
    - identidade canônica;
    - scores;
    - timestamps de criação/atualização.
    """
    validar_candidato_openmeteo(
        candidato
    )

    status = mapear_status_canonico(
        candidato
    )

    if status not in CANONICAL_STATUSES:
        raise ValueError(
            "Status canônico inválido: "
            f"{status!r}."
        )

    (
        expected_intensity,
        observed_intensity,
    ) = mapear_intensidades_canonicas(
        candidato=candidato,
        status_canonico=status,
    )

    localizacao = (
        construir_localizacao_canonica(
            candidato
        )
    )

    return {
        "canonical_name": (
            construir_nome_canonico(
                candidato
            )
        ),
        "summary": candidato.summary,
        "event_type": (
            CANONICAL_EVENT_TYPE
        ),
        "primary_category": (
            CANONICAL_PRIMARY_CATEGORY
        ),
        "subcategory": (
            mapear_subcategoria(
                candidato.event_type
            )
        ),
        "start_at_utc": (
            converter_datetime_para_utc(
                candidato.start_at
            )
        ),
        "end_at_utc": (
            converter_datetime_para_utc(
                candidato.end_at
            )
        ),
        "timezone_original": (
            candidato.timezone
        ),
        "known_at_utc": (
            converter_datetime_para_utc(
                candidato.known_at
            )
        ),
        "status": status,
        "scope": (
            CANONICAL_SCOPE
        ),
        "expected_intensity": (
            expected_intensity
        ),
        "observed_intensity": (
            observed_intensity
        ),
        "locations": [
            localizacao
        ],
        "sources": (
            construir_sources_base(
                candidato
            )
        ),
        "evidence": (
            construir_evidence_base(
                candidato
            )
        ),
    }


def mapear_candidatos_base(
    candidatos: list[EventCandidate],
) -> list[dict[str, Any]]:
    """
    Aplica o mapeamento base a uma coleção de
    candidatos e mantém uma ordem determinística.
    """
    resultados = [
        mapear_candidato_base(
            candidato
        )
        for candidato in candidatos
    ]

    resultados.sort(
        key=lambda item: (
            str(
                item[
                    "start_at_utc"
                ]
            ),
            str(
                item[
                    "subcategory"
                ]
            ),
            str(
                item[
                    "canonical_name"
                ]
            ),
        )
    )

    return resultados
