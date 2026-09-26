from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openmeteo_pipeline.config import (
    BASE_DIR,
    EVENT_RULES_CONFIG_PATH,
    STAGING_DAILY_CONSOLIDATED_PATH,
    STAGING_EVENTS_DIR,
    TEMPERATURE_BASELINE_CONSOLIDATED_PATH,
    WEATHER_DETECTOR_VERSION,
    WEATHER_EVENT_CANDIDATES_MANIFEST_PATH,
    WEATHER_EVENT_CANDIDATES_PATH,
    WEATHER_EVENT_SUMMARY_JSON_PATH,
    WEATHER_EVENT_SUMMARY_CSV_PATH,
    WEATHER_EVENT_SUMMARY_TXT_PATH,
)
from openmeteo_pipeline.models import EventCandidate
from openmeteo_pipeline.storage import agora_utc_iso, salvar_json
from openmeteo_pipeline.reports import (
    salvar_relatorio_climatico,
)

EVENT_TITLES = {
    "unusually_hot_day": "Dia excepcionalmente quente",
    "extreme_heat_day": "Dia de calor extremo",
    "heat_wave_candidate": "Candidato a onda de calor",
    "unusually_cold_day": "Dia excepcionalmente frio",
    "extreme_cold_day": "Dia de frio extremo",
    "cold_wave_candidate": "Candidato a onda de frio",
    "heavy_rain_day": "Dia de chuva intensa",
    "extreme_rain_day": "Dia de chuva extrema",
    "strong_wind_day": "Dia de vento forte",
    "severe_wind_day": "Dia de ventania severa",
    "extreme_wind_day": "Dia de ventania extrema",
    "storm_candidate": "Candidato a tempestade",
}


EVENT_KEYWORDS = {
    "unusually_hot_day": [
        "calor",
        "temperatura elevada",
        "dia quente",
    ],
    "extreme_heat_day": [
        "calor extremo",
        "temperatura extrema",
        "estresse térmico",
    ],
    "heat_wave_candidate": [
        "onda de calor",
        "calor persistente",
        "noites quentes",
    ],
    "unusually_cold_day": [
        "frio",
        "temperatura baixa",
        "dia frio",
    ],
    "extreme_cold_day": [
        "frio extremo",
        "temperatura extrema",
        "estresse térmico",
    ],
    "cold_wave_candidate": [
        "onda de frio",
        "frio persistente",
        "queda de temperatura",
    ],
    "heavy_rain_day": [
        "chuva intensa",
        "precipitação",
        "alagamento",
    ],
    "extreme_rain_day": [
        "chuva extrema",
        "precipitação extrema",
        "alagamento",
        "deslizamento",
    ],
    "strong_wind_day": [
        "vento forte",
        "rajada de vento",
        "ventania",
    ],
    "severe_wind_day": [
        "ventania severa",
        "rajada severa",
        "vento intenso",
    ],
    "extreme_wind_day": [
        "ventania extrema",
        "rajada extrema",
        "vento severo",
    ],
    "storm_candidate": [
        "tempestade",
        "temporal",
        "chuva e vento",
        "trovoada",
    ],
}

# =============================================================================
# QUALIDADE DOS REGISTROS DIÁRIOS
# =============================================================================

DETECTABLE_DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_gusts_10m_max",
)


def carregar_json_objeto(caminho: Path) -> dict[str, Any]:
    """Carrega um arquivo JSON que deve conter um objeto."""
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    with caminho.open("r", encoding="utf-8") as arquivo:
        payload = json.load(arquivo)

    if not isinstance(payload, dict):
        raise ValueError(
            "O arquivo deveria conter um objeto JSON: "
            f"{caminho}"
        )

    return payload


def carregar_regras_clima() -> dict[str, Any]:
    """Carrega e valida as seções mínimas das regras climáticas."""
    payload = carregar_json_objeto(EVENT_RULES_CONFIG_PATH)

    rules_version = payload.get("rules_version")

    if not isinstance(rules_version, str) or not rules_version.strip():
        raise ValueError(
            "event_rules.json não contém rules_version válido."
        )

    secoes_obrigatorias = {
        "temperature_events": (
            "unusually_hot_day",
            "extreme_heat_day",
            "heat_wave_candidate",
            "unusually_cold_day",
            "extreme_cold_day",
            "cold_wave_candidate",
        ),
        "precipitation_events": (
            "heavy_rain_day",
            "extreme_rain_day",
        ),
        "wind_events": (
            "strong_wind_day",
            "severe_wind_day",
            "extreme_wind_day",
        ),
        "storm_events": ("storm_candidate",),
    }

    ausencias: list[str] = []

    for nome_secao, nomes_regras in secoes_obrigatorias.items():
        secao = payload.get(nome_secao)

        if not isinstance(secao, dict):
            ausencias.append(nome_secao)
            continue

        for nome_regra in nomes_regras:
            if not isinstance(secao.get(nome_regra), dict):
                ausencias.append(f"{nome_secao}.{nome_regra}")

    if ausencias:
        raise ValueError(
            "Regras climáticas ausentes ou inválidas: "
            f"{ausencias}"
        )

    return payload

def registro_tem_dados_detectaveis(
    registro: dict[str, Any],
) -> bool:
    """
    Informa se o registro possui ao menos uma
    variável capaz de alimentar os detectores.
    """
    return any(
        registro.get(campo) is not None
        for campo in DETECTABLE_DAILY_FIELDS
    )


def validar_continuidade_registros(
    registros: list[dict[str, Any]],
) -> None:
    """
    Impede que o detector opere silenciosamente
    sobre uma série diária com datas ausentes.

    A validação ocorre separadamente para cada
    localidade.
    """
    grupos: dict[str, list[date]] = {}

    for registro in registros:
        slug = str(
            registro["location_slug"]
        )

        data_registro = date.fromisoformat(
            str(registro["date_local"])
        )

        grupos.setdefault(
            slug,
            [],
        ).append(
            data_registro
        )

    for slug, datas in grupos.items():
        datas_ordenadas = sorted(datas)

        if len(datas_ordenadas) != len(
            set(datas_ordenadas)
        ):
            raise ValueError(
                "Existem datas duplicadas no staging "
                f"diário da localidade {slug}."
            )

        lacunas: list[str] = []

        for anterior, atual in zip(
            datas_ordenadas,
            datas_ordenadas[1:],
        ):
            esperado = anterior + timedelta(
                days=1
            )

            if atual != esperado:
                lacunas.append(
                    f"{anterior.isoformat()}"
                    " -> "
                    f"{atual.isoformat()}"
                )

        if lacunas:
            raise ValueError(
                "O staging diário possui lacunas "
                f"para {slug}: {lacunas}. "
                "Atualize histórico e previsão antes "
                "de executar o detector."
            )

        

def carregar_registros_diarios() -> list[dict[str, Any]]:
    """Carrega os registros do staging diário consolidado."""
    payload = carregar_json_objeto(
        STAGING_DAILY_CONSOLIDATED_PATH
    )

    registros = payload.get("records")

    if not isinstance(registros, list):
        raise ValueError(
            "O staging diário não contém uma lista em records."
        )

    resultado: list[dict[str, Any]] = []

    campos_obrigatorios = (
        "daily_weather_id",
        "source_service",
        "data_kind",
        "location_slug",
        "location_name",
        "country_code",
        "latitude",
        "longitude",
        "timezone",
        "date_local",
        "raw_record_id",
        "raw_payload_hash",
        "retrieved_at_utc",
    )

    for posicao, registro in enumerate(registros, start=1):
        if not isinstance(registro, dict):
            raise ValueError(
                f"Registro diário inválido na posição {posicao}."
            )

        campos_ausentes = [
            campo
            for campo in campos_obrigatorios
            if registro.get(campo) is None
        ]

        if campos_ausentes:
            raise ValueError(
                f"Registro diário {posicao} sem campos: "
                f"{campos_ausentes}"
            )

        if not registro_tem_dados_detectaveis(registro):
            logging.warning(
                "Registro diário ignorado por não "
                "possuir dados meteorológicos "
                "detectáveis: %s | %s",
                registro["location_slug"],
                registro["date_local"],
            )
            continue

        resultado.append(registro)

    if not resultado:
        raise ValueError(
            "Nenhum registro diário foi encontrado."
        )

    resultado.sort(
        key=lambda item: (
            str(item["location_slug"]),
            str(item["date_local"]),
        )
    )

    validar_continuidade_registros(
        resultado
    )

    return resultado



def carregar_indice_baseline(
) -> dict[str, dict[str, Any]]:
    """
    Carrega a baseline térmica e cria um índice
    por location_slug.

    O Detector 1.2 exige a baseline 1.1 porque
    necessita da média climatológica mensal para
    calcular as anomalias térmicas.
    """
    payload = carregar_json_objeto(
        TEMPERATURE_BASELINE_CONSOLIDATED_PATH
    )

    baseline_version = payload.get(
        "baseline_version"
    )

    if baseline_version != "1.1":
        raise ValueError(
            (
                "O Detector 1.2 exige "
                "temperature baseline 1.1. "
                "Versão encontrada: "
                f"{baseline_version}."
            )
        )

    localidades = payload.get(
        "locations"
    )

    if not isinstance(
        localidades,
        list,
    ):
        raise ValueError(
            (
                "A baseline consolidada não "
                "contém uma lista em locations."
            )
        )

    indice: dict[
        str,
        dict[str, Any],
    ] = {}

    for posicao, localidade in enumerate(
        localidades,
        start=1,
    ):
        if not isinstance(
            localidade,
            dict,
        ):
            raise ValueError(
                (
                    "Baseline inválida na posição "
                    f"{posicao}."
                )
            )

        slug = localidade.get(
            "location_slug"
        )

        if (
            not isinstance(slug, str)
            or not slug
        ):
            raise ValueError(
                (
                    "Baseline sem location_slug "
                    f"válido na posição {posicao}."
                )
            )

        if slug in indice:
            raise ValueError(
                (
                    "Baseline duplicada para a "
                    f"localidade: {slug}"
                )
            )

        meses = localidade.get(
            "months"
        )

        if not isinstance(
            meses,
            list,
        ):
            raise ValueError(
                (
                    "Baseline sem months para "
                    f"{slug}."
                )
            )

        if len(meses) != 12:
            raise ValueError(
                (
                    "Baseline deveria possuir "
                    f"12 meses para {slug}, mas "
                    f"possui {len(meses)}."
                )
            )

        for item_mes in meses:
            if not isinstance(
                item_mes,
                dict,
            ):
                raise ValueError(
                    (
                        "Mês inválido na baseline "
                        f"de {slug}."
                    )
                )

            thresholds = item_mes.get(
                "thresholds"
            )

            if not isinstance(
                thresholds,
                dict,
            ):
                raise ValueError(
                    (
                        "Thresholds ausentes na "
                        f"baseline de {slug}."
                    )
                )

            for metrica in (
                "temperature_2m_max",
                "temperature_2m_min",
            ):
                estatisticas = (
                    thresholds.get(
                        metrica
                    )
                )

                if not isinstance(
                    estatisticas,
                    dict,
                ):
                    raise ValueError(
                        (
                            "Estatísticas ausentes "
                            f"para {metrica} em "
                            f"{slug}."
                        )
                    )

                for chave in (
                    "mean",
                    "p05",
                    "p10",
                    "p90",
                    "p95",
                ):
                    valor = (
                        estatisticas.get(
                            chave
                        )
                    )

                    if not isinstance(
                        valor,
                        (int, float),
                    ):
                        raise ValueError(
                            (
                                f"{slug}: "
                                f"{metrica}.{chave} "
                                "não possui valor "
                                "numérico válido."
                            )
                        )

        indice[
            slug
        ] = localidade

    if not indice:
        raise ValueError(
            (
                "Nenhuma baseline térmica "
                "foi encontrada."
            )
        )

    return indice


def agrupar_registros_por_localidade(
    registros: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Agrupa e ordena registros diários por localidade."""
    grupos: dict[str, list[dict[str, Any]]] = {}

    for registro in registros:
        slug = str(registro["location_slug"])
        grupos.setdefault(slug, []).append(registro)

    for grupo in grupos.values():
        grupo.sort(key=lambda item: str(item["date_local"]))

    return grupos


def obter_mes(data_local: str) -> int:
    """Extrai o mês de uma data local ISO."""
    return date.fromisoformat(data_local).month


def obter_estatistica_baseline(
    baseline_localidade: dict[str, Any],
    data_local: str,
    metrica: str,
    estatistica: str,
) -> float:
    """
    Obtém uma estatística térmica mensal da
    baseline.

    Estatísticas atualmente esperadas:
    - mean;
    - p05;
    - p10;
    - p90;
    - p95.
    """
    meses = baseline_localidade.get(
        "months"
    )

    if not isinstance(
        meses,
        list,
    ):
        raise ValueError(
            (
                "Baseline da localidade não "
                "contém uma lista em months."
            )
        )

    mes_alvo = obter_mes(
        data_local
    )

    for item_mes in meses:
        if not isinstance(
            item_mes,
            dict,
        ):
            continue

        if (
            item_mes.get("month")
            != mes_alvo
        ):
            continue

        thresholds = item_mes.get(
            "thresholds"
        )

        if not isinstance(
            thresholds,
            dict,
        ):
            break

        thresholds_metrica = (
            thresholds.get(
                metrica
            )
        )

        if not isinstance(
            thresholds_metrica,
            dict,
        ):
            break

        valor = (
            thresholds_metrica.get(
                estatistica
            )
        )

        if isinstance(
            valor,
            (int, float),
        ):
            return float(
                valor
            )

        break

    raise ValueError(
        (
            "Estatística da baseline não "
            "encontrada para "
            f"mês={mes_alvo}, "
            f"métrica={metrica}, "
            f"estatística={estatistica}."
        )
    )



def obter_limiar_percentil(
    baseline_localidade: dict[str, Any],
    data_local: str,
    metrica: str,
    percentil: str,
) -> float:
    """
    Obtém um percentil mensal da baseline
    térmica.
    """
    return obter_estatistica_baseline(
        baseline_localidade=(
            baseline_localidade
        ),
        data_local=data_local,
        metrica=metrica,
        estatistica=percentil,
    )


def comparar(valor: float, limiar: float, operador: str) -> bool:
    """Executa os operadores aceitos pelas regras."""
    if operador == "greater_than_or_equal":
        return valor >= limiar

    if operador == "less_than_or_equal":
        return valor <= limiar

    if operador == "greater_than":
        return valor > limiar

    if operador == "less_than":
        return valor < limiar

    raise ValueError(
        f"Operador não reconhecido: {operador}"
    )


def criar_candidate_id(external_id: str) -> str:
    """Gera um identificador determinístico para o candidato."""
    hash_id = hashlib.sha256(
        external_id.encode("utf-8")
    ).hexdigest()

    return f"weather-{hash_id[:24]}"


def criar_intervalo_local(
    data_inicial: str,
    data_final: str,
    timezone_name: str,
) -> tuple[str, str]:
    """Cria o intervalo completo de um ou mais dias locais."""
    try:
        timezone_local = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as erro:
        raise ValueError(
            f"Timezone inválido: {timezone_name}"
        ) from erro

    inicio_data = date.fromisoformat(data_inicial)
    fim_data = date.fromisoformat(data_final)

    inicio = datetime.combine(
        inicio_data,
        time.min,
        tzinfo=timezone_local,
    )

    fim = datetime.combine(
        fim_data + timedelta(days=1),
        time.min,
        tzinfo=timezone_local,
    ) - timedelta(microseconds=1)

    return inicio.isoformat(), fim.isoformat()


def parsear_datetime_iso(valor: str) -> datetime:
    """Converte timestamps ISO, aceitando sufixo Z."""
    texto = valor.strip()

    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"

    return datetime.fromisoformat(texto)


def calcular_horizonte_previsao(
    registro: dict[str, Any],
) -> int | None:
    """
    Calcula o horizonte da previsão em dias
    calendários locais.

    Exemplo:
    previsão coletada em 07/08 para 16/08
    -> horizonte = 9 dias.
    """
    if str(
        registro["data_kind"]
    ) != "forecast":
        return None

    timezone_name = str(
        registro["timezone"]
    )

    try:
        timezone_local = ZoneInfo(
            timezone_name
        )
    except ZoneInfoNotFoundError as erro:
        raise ValueError(
            "Timezone inválido ao calcular "
            f"horizonte: {timezone_name}"
        ) from erro

    retrieved_at = parsear_datetime_iso(
        str(
            registro[
                "retrieved_at_utc"
            ]
        )
    )

    retrieved_local = (
        retrieved_at.astimezone(
            timezone_local
        )
    )

    data_previsao = date.fromisoformat(
        str(
            registro["date_local"]
        )
    )

    return (
        data_previsao
        - retrieved_local.date()
    ).days

def extrair_contexto_previsao(
    registros: list[dict[str, Any]],
) -> tuple[list[str], list[int]]:
    """
    Retorna as referências temporais e horizontes
    dos registros de previsão utilizados pelo
    candidato.
    """
    referencias: set[str] = set()
    horizontes: set[int] = set()

    for registro in registros:
        if str(
            registro["data_kind"]
        ) != "forecast":
            continue

        referencias.add(
            str(
                registro[
                    "retrieved_at_utc"
                ]
            )
        )

        horizonte = (
            calcular_horizonte_previsao(
                registro
            )
        )

        if horizonte is not None:
            horizontes.add(
                horizonte
            )

    return (
        sorted(referencias),
        sorted(horizontes),
    )


def obter_known_at(registros: list[dict[str, Any]]) -> str:
    """Seleciona o instante de coleta mais recente."""
    pares = [
        (
            parsear_datetime_iso(str(registro["retrieved_at_utc"])),
            str(registro["retrieved_at_utc"]),
        )
        for registro in registros
    ]

    pares.sort(key=lambda item: item[0])

    return pares[-1][1]


def determinar_status(registros: list[dict[str, Any]]) -> str:
    """Resume a natureza temporal dos registros do candidato."""
    data_kinds = {
        str(registro["data_kind"])
        for registro in registros
    }

    if data_kinds == {"forecast"}:
        return "forecast"

    if data_kinds == {"historical_reanalysis"}:
        return "historical_reanalysis"

    if data_kinds == {"historical_provisional"}:
        return "provisional"

    return "mixed"


def extrair_proveniencia(
    registros: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    """Extrai IDs diários, RAWs e hashes sem duplicidade."""
    source_record_ids = sorted(
        {
            str(registro["raw_record_id"])
            for registro in registros
        }
    )

    source_payload_hashes = sorted(
        {
            str(registro["raw_payload_hash"])
            for registro in registros
        }
    )

    daily_weather_ids = sorted(
        {
            str(registro["daily_weather_id"])
            for registro in registros
        }
    )

    return (
        source_record_ids,
        source_payload_hashes,
        daily_weather_ids,
    )


def construir_candidato(
    *,
    event_type: str,
    registros: list[dict[str, Any]],
    regra: dict[str, Any],
    metrics: dict[str, Any],
    summary: str,
    rules_version: str,
    extra_data: dict[str, Any] | None = None,
) -> EventCandidate:
    """Constrói o contrato compartilhado EventCandidate."""
    if not registros:
        raise ValueError(
            "Não é possível construir candidato sem registros."
        )

    registros_ordenados = sorted(
        registros,
        key=lambda item: str(item["date_local"]),
    )

    primeiro = registros_ordenados[0]
    ultimo = registros_ordenados[-1]

    location_slug = str(primeiro["location_slug"])
    city_name = str(primeiro["location_name"])
    timezone_name = str(primeiro["timezone"])
    data_inicial = str(primeiro["date_local"])
    data_final = str(ultimo["date_local"])

    start_at, end_at = criar_intervalo_local(
        data_inicial=data_inicial,
        data_final=data_final,
        timezone_name=timezone_name,
    )

    external_id = (
        f"openmeteo-derived:{event_type}:"
        f"{location_slug}:{data_inicial}:"
        f"{data_final}:{rules_version}"
    )

    (
        source_record_ids,
        source_payload_hashes,
        daily_weather_ids,
    ) = extrair_proveniencia(
        registros_ordenados
    )

    (
        forecast_reference_times_utc,
        forecast_horizon_days,
    ) = extrair_contexto_previsao(
        registros_ordenados
    )

    candidate_id = criar_candidate_id(
        external_id
    )

    event_family = str(
        regra["family"]
    )
    severity = str(regra["severity"])

    dados_extras: dict[str, Any] = {
        "derived": True,
        "forecast_reference_times_utc": (
            forecast_reference_times_utc
        ),
        "forecast_horizon_days": (
            forecast_horizon_days[0]
            if len(
                forecast_horizon_days
            ) == 1
            else None
        ),
        "forecast_horizon_min_days": (
            min(
                forecast_horizon_days
            )
            if forecast_horizon_days
            else None
        ),
        "forecast_horizon_max_days": (
            max(
                forecast_horizon_days
            )
            if forecast_horizon_days
            else None
        ),
        "event_granularity": (
            "day"
            if len(
                registros_ordenados
            ) == 1
            else "multi_day"
        ),
        "data_kinds": sorted(
            {
                str(registro["data_kind"])
                for registro in registros_ordenados
            }
        ),
        "record_count": len(registros_ordenados),
    }

    if extra_data:
        dados_extras.update(extra_data)

    return EventCandidate(
        candidate_id=candidate_id,
        source="open-meteo",
        source_service="weather_detector",
        event_type=event_type,
        event_family=event_family,
        severity=severity,
        title=f"{EVENT_TITLES[event_type]} em {city_name}",
        summary=summary,
        start_at=start_at,
        end_at=end_at,
        timezone=timezone_name,
        known_at=obter_known_at(registros_ordenados),
        status=determinar_status(registros_ordenados),
        country_code=str(primeiro["country_code"]),
        state_code=(
            str(primeiro["state_code"])
            if primeiro.get("state_code") is not None
            else None
        ),
        city_name=city_name,
        location_slug=location_slug,
        latitude=float(primeiro["latitude"]),
        longitude=float(primeiro["longitude"]),
        metrics=metrics,
        rule=dict(regra),
        source_record_ids=source_record_ids,
        source_payload_hashes=source_payload_hashes,
        daily_weather_ids=daily_weather_ids,
        keywords=list(EVENT_KEYWORDS[event_type]),
        detector_version=WEATHER_DETECTOR_VERSION,
        rules_version=rules_version,
        extra_data=dados_extras,
    )


def avaliar_regra_percentil(
    registro: dict[str, Any],
    baseline_localidade: dict[str, Any],
    regra: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Avalia uma regra térmica baseada em
    percentil mensal e, quando configurado,
    também na magnitude da anomalia em relação
    à média climatológica mensal.

    Uma regra pode portanto exigir:

    1. ultrapassagem do percentil;
    2. ultrapassagem de um limiar de anomalia.

    Regras sem anomaly_operator continuam sendo
    exclusivamente percentílicas.
    """
    if regra.get(
        "enabled"
    ) is not True:
        return None

    metrica = str(
        regra["metric"]
    )

    operador = str(
        regra["operator"]
    )

    percentil = str(
        regra["percentile"]
    )

    valor_bruto = registro.get(
        metrica
    )

    if valor_bruto is None:
        return None

    data_local = str(
        registro["date_local"]
    )

    valor = float(
        valor_bruto
    )

    limiar_percentil = (
        obter_estatistica_baseline(
            baseline_localidade=(
                baseline_localidade
            ),
            data_local=data_local,
            metrica=metrica,
            estatistica=percentil,
        )
    )

    media_climatologica = (
        obter_estatistica_baseline(
            baseline_localidade=(
                baseline_localidade
            ),
            data_local=data_local,
            metrica=metrica,
            estatistica="mean",
        )
    )

    passou_percentil = comparar(
        valor,
        limiar_percentil,
        operador,
    )

    if not passou_percentil:
        return None

    anomalia = round(
        valor
        - media_climatologica,
        3,
    )

    anomaly_operator = regra.get(
        "anomaly_operator"
    )

    anomaly_threshold_raw = regra.get(
        "anomaly_threshold_c"
    )

    passou_anomalia = True

    anomaly_threshold: float | None = None

    if anomaly_operator is not None:
        if anomaly_threshold_raw is None:
            raise ValueError(
                (
                    "Regra térmica possui "
                    "anomaly_operator mas não "
                    "anomaly_threshold_c."
                )
            )

        anomaly_threshold = float(
            anomaly_threshold_raw
        )

        passou_anomalia = comparar(
            anomalia,
            anomaly_threshold,
            str(anomaly_operator),
        )

        if not passou_anomalia:
            return None

    return {
        "date_local": data_local,
        "metric": metrica,
        "value": valor,
        "operator": operador,

        "threshold_type": (
            "monthly_percentile"
        ),
        "percentile": percentil,
        "threshold_value": (
            limiar_percentil
        ),
        "distance_from_threshold": round(
            valor
            - limiar_percentil,
            3,
        ),

        "climatological_mean": (
            media_climatologica
        ),
        "anomaly_from_mean_c": (
            anomalia
        ),

        "anomaly_required": (
            anomaly_operator
            is not None
        ),
        "anomaly_operator": (
            str(anomaly_operator)
            if anomaly_operator
            is not None
            else None
        ),
        "anomaly_threshold_c": (
            anomaly_threshold
        ),
        "anomaly_condition_met": (
            passou_anomalia
        ),
    }


def avaliar_regra_absoluta(
    registro: dict[str, Any],
    regra: dict[str, Any],
) -> dict[str, Any] | None:
    """Avalia uma regra diária com limiar absoluto."""
    if regra.get("enabled") is not True:
        return None

    metrica = str(regra["metric"])
    operador = str(regra["operator"])
    limiar = float(regra["threshold"])

    valor_bruto = registro.get(metrica)

    if valor_bruto is None:
        return None

    valor = float(valor_bruto)

    if not comparar(valor, limiar, operador):
        return None

    return {
        "date_local": str(registro["date_local"]),
        "metric": metrica,
        "value": valor,
        "operator": operador,
        "threshold_type": "absolute",
        "threshold_value": limiar,
        "unit": regra.get("unit"),
        "distance_from_threshold": round(valor - limiar, 3),
    }


def construir_resumo_termico_diario(
    event_type: str,
    cidade: str,
    detalhe: dict[str, Any],
) -> str:
    """
    Resume um candidato térmico diário,
    explicitando percentil, média climatológica
    e anomalia.
    """
    valor = float(
        detalhe["value"]
    )

    limiar = float(
        detalhe["threshold_value"]
    )

    media = float(
        detalhe["climatological_mean"]
    )

    anomalia = float(
        detalhe["anomaly_from_mean_c"]
    )

    percentil = str(
        detalhe["percentile"]
    )

    resumo = (
        f"{EVENT_TITLES[event_type]} "
        f"em {cidade}: "
        f"{detalhe['metric']} de "
        f"{valor:.1f} °C, "
        f"limiar local {percentil} de "
        f"{limiar:.1f} °C, "
        f"média climatológica de "
        f"{media:.1f} °C e "
        f"anomalia de "
        f"{anomalia:+.1f} °C."
    )

    anomaly_threshold = (
        detalhe.get(
            "anomaly_threshold_c"
        )
    )

    if anomaly_threshold is not None:
        resumo += (
            " O evento também satisfez "
            "o limiar operacional de "
            "anomalia de "
            f"{float(anomaly_threshold):+.1f} °C."
        )

    return resumo


def construir_resumo_absoluto(
    event_type: str,
    cidade: str,
    detalhe: dict[str, Any],
) -> str:
    """Resume candidatos de chuva, vento ou tempestade."""
    if event_type in {"heavy_rain_day", "extreme_rain_day"}:
        return (
            f"{EVENT_TITLES[event_type]} em {cidade}: "
            f"precipitação acumulada de {detalhe['value']:.1f} mm, "
            f"comparada ao limiar operacional de "
            f"{detalhe['threshold_value']:.1f} mm/dia."
        )

    if event_type in {
        "strong_wind_day",
        "severe_wind_day",
        "extreme_wind_day",
    }:
        return (
            f"{EVENT_TITLES[event_type]} em {cidade}: "
            f"rajada máxima de {detalhe['value']:.1f} km/h, "
            f"comparada ao limiar operacional de "
            f"{detalhe['threshold_value']:.1f} km/h."
        )

    if event_type == "storm_candidate":
        condicoes = detalhe.get("matched_conditions", [])

        return (
            f"Candidato a tempestade em {cidade}: "
            + "; ".join(str(item) for item in condicoes)
            + "."
        )

    raise ValueError(
        f"Tipo de evento sem resumo absoluto: {event_type}"
    )


def detectar_eventos_termicos_diarios(
    registros: list[dict[str, Any]],
    baseline_localidade: dict[str, Any],
    regras: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """
    Detecta eventos térmicos diários.

    Para calor e frio, somente o nível de maior
    severidade satisfeito é gerado.

    Exemplos:
    - um dia extreme_heat_day não gera também
      unusually_hot_day;
    - um dia extreme_cold_day não gera também
      unusually_cold_day.
    """
    candidatos: list[
        EventCandidate
    ] = []

    pares_priorizados = (
        (
            "extreme_heat_day",
            "unusually_hot_day",
        ),
        (
            "extreme_cold_day",
            "unusually_cold_day",
        ),
    )

    for registro in registros:
        for (
            evento_prioritario,
            evento_secundario,
        ) in pares_priorizados:

            detalhe = (
                avaliar_regra_percentil(
                    registro=registro,
                    baseline_localidade=(
                        baseline_localidade
                    ),
                    regra=regras[
                        evento_prioritario
                    ],
                )
            )

            event_type = (
                evento_prioritario
            )

            if detalhe is None:
                detalhe = (
                    avaliar_regra_percentil(
                        registro=registro,
                        baseline_localidade=(
                            baseline_localidade
                        ),
                        regra=regras[
                            evento_secundario
                        ],
                    )
                )

                event_type = (
                    evento_secundario
                )

            if detalhe is None:
                continue

            cidade = str(
                registro[
                    "location_name"
                ]
            )

            candidatos.append(
                construir_candidato(
                    event_type=(
                        event_type
                    ),
                    registros=[
                        registro
                    ],
                    regra=regras[
                        event_type
                    ],
                    metrics={
                        "primary": detalhe,
                    },
                    summary=(
                        construir_resumo_termico_diario(
                            event_type,
                            cidade,
                            detalhe,
                        )
                    ),
                    rules_version=(
                        rules_version
                    ),
                )
            )

    return candidatos


def datas_sao_consecutivas(
    data_anterior: str,
    data_atual: str,
) -> bool:
    """Confirma se duas datas locais são consecutivas."""
    anterior = date.fromisoformat(data_anterior)
    atual = date.fromisoformat(data_atual)

    return atual == anterior + timedelta(days=1)


def separar_sequencias_consecutivas(
    itens: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[list[tuple[dict[str, Any], dict[str, Any]]]]:
    """Divide avaliações aprovadas em sequências sem lacunas."""
    if not itens:
        return []

    itens_ordenados = sorted(
        itens,
        key=lambda item: str(item[0]["date_local"]),
    )

    sequencias: list[
        list[tuple[dict[str, Any], dict[str, Any]]]
    ] = []

    sequencia_atual = [itens_ordenados[0]]

    for item in itens_ordenados[1:]:
        registro_anterior = sequencia_atual[-1][0]
        registro_atual = item[0]

        if datas_sao_consecutivas(
            str(registro_anterior["date_local"]),
            str(registro_atual["date_local"]),
        ):
            sequencia_atual.append(item)
            continue

        sequencias.append(sequencia_atual)
        sequencia_atual = [item]

    sequencias.append(sequencia_atual)

    return sequencias


def detectar_heat_wave_candidates(
    registros: list[dict[str, Any]],
    baseline_localidade: dict[str, Any],
    regra: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """
    Detecta candidatos a onda de calor.

    Um dia somente participa da sequência quando
    satisfaz simultaneamente:

    - o percentil térmico configurado;
    - a magnitude mínima da anomalia em relação
      à média climatológica.

    A sequência precisa possuir ao menos
    minimum_consecutive_days.

    Noites quentes continuam sendo calculadas
    como evidência complementar, mas não são uma
    condição obrigatória para o evento.
    """
    if regra.get(
        "enabled"
    ) is not True:
        return []

    dias_aprovados: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ] = []

    for registro in registros:
        detalhe = (
            avaliar_regra_percentil(
                registro=registro,
                baseline_localidade=(
                    baseline_localidade
                ),
                regra=regra,
            )
        )

        if detalhe is not None:
            dias_aprovados.append(
                (
                    registro,
                    detalhe,
                )
            )

    minimo_dias = int(
        regra[
            "minimum_consecutive_days"
        ]
    )

    metrica_noite = str(
        regra.get(
            "warm_night_metric",
            "temperature_2m_min",
        )
    )

    percentil_noite = str(
        regra.get(
            "warm_night_percentile",
            "p90",
        )
    )

    candidatos: list[
        EventCandidate
    ] = []

    sequencias = (
        separar_sequencias_consecutivas(
            dias_aprovados
        )
    )

    for sequencia in sequencias:
        if len(
            sequencia
        ) < minimo_dias:
            continue

        registros_sequencia = [
            item[0]
            for item in sequencia
        ]

        detalhes_dias = [
            item[1]
            for item in sequencia
        ]

        detalhes_noites: list[
            dict[str, Any]
        ] = []

        # -----------------------------------------------------
        # NOITES QUENTES COMO EVIDÊNCIA COMPLEMENTAR
        # -----------------------------------------------------

        for registro in registros_sequencia:
            valor_bruto = registro.get(
                metrica_noite
            )

            if valor_bruto is None:
                continue

            data_local = str(
                registro[
                    "date_local"
                ]
            )

            valor = float(
                valor_bruto
            )

            limiar_noite = (
                obter_estatistica_baseline(
                    baseline_localidade=(
                        baseline_localidade
                    ),
                    data_local=(
                        data_local
                    ),
                    metrica=(
                        metrica_noite
                    ),
                    estatistica=(
                        percentil_noite
                    ),
                )
            )

            media_noite = (
                obter_estatistica_baseline(
                    baseline_localidade=(
                        baseline_localidade
                    ),
                    data_local=(
                        data_local
                    ),
                    metrica=(
                        metrica_noite
                    ),
                    estatistica="mean",
                )
            )

            if valor >= limiar_noite:
                detalhes_noites.append(
                    {
                        "date_local": (
                            data_local
                        ),
                        "metric": (
                            metrica_noite
                        ),
                        "value": valor,
                        "percentile": (
                            percentil_noite
                        ),
                        "threshold_value": (
                            limiar_noite
                        ),
                        "climatological_mean": (
                            media_noite
                        ),
                        "anomaly_from_mean_c": round(
                            valor
                            - media_noite,
                            3,
                        ),
                    }
                )

        # -----------------------------------------------------
        # MÉTRICAS DA SEQUÊNCIA
        # -----------------------------------------------------

        valores = [
            float(
                detalhe["value"]
            )
            for detalhe
            in detalhes_dias
        ]

        medias_climatologicas = [
            float(
                detalhe[
                    "climatological_mean"
                ]
            )
            for detalhe
            in detalhes_dias
        ]

        anomalias = [
            float(
                detalhe[
                    "anomaly_from_mean_c"
                ]
            )
            for detalhe
            in detalhes_dias
        ]

        temperatura_media_periodo = (
            sum(valores)
            / len(valores)
        )

        media_climatologica_periodo = (
            sum(
                medias_climatologicas
            )
            / len(
                medias_climatologicas
            )
        )

        anomalia_media_periodo = (
            sum(anomalias)
            / len(anomalias)
        )

        anomalia_maxima = max(
            anomalias
        )

        cidade = str(
            registros_sequencia[
                0
            ][
                "location_name"
            ]
        )

        data_inicial = str(
            registros_sequencia[
                0
            ][
                "date_local"
            ]
        )

        data_final = str(
            registros_sequencia[
                -1
            ][
                "date_local"
            ]
        )

        summary = (
            f"Candidato a onda de calor "
            f"em {cidade} entre "
            f"{data_inicial} e "
            f"{data_final}: "
            f"{len(registros_sequencia)} "
            "dias consecutivos satisfazendo "
            f"{regra['percentile']} e "
            "anomalia mínima diária de "
            f"{float(regra['anomaly_threshold_c']):+.1f} °C. "
            "A média das máximas do período "
            f"foi {temperatura_media_periodo:.1f} °C, "
            "contra média climatológica de "
            f"{media_climatologica_periodo:.1f} °C, "
            "com anomalia média de "
            f"{anomalia_media_periodo:+.1f} °C."
        )

        candidatos.append(
            construir_candidato(
                event_type=(
                    "heat_wave_candidate"
                ),
                registros=(
                    registros_sequencia
                ),
                regra=regra,
                metrics={
                    "hot_days": (
                        detalhes_dias
                    ),
                    "warm_nights": (
                        detalhes_noites
                    ),
                    "period": {
                        "day_count": len(
                            registros_sequencia
                        ),
                        "mean_temperature_c": round(
                            temperatura_media_periodo,
                            3,
                        ),
                        "mean_climatological_temperature_c": round(
                            media_climatologica_periodo,
                            3,
                        ),
                        "mean_anomaly_c": round(
                            anomalia_media_periodo,
                            3,
                        ),
                        "maximum_anomaly_c": round(
                            anomalia_maxima,
                            3,
                        ),
                        "warm_night_count": len(
                            detalhes_noites
                        ),
                    },
                },
                summary=summary,
                rules_version=(
                    rules_version
                ),
                extra_data={
                    "warm_nights": len(
                        detalhes_noites
                    ),
                    "wave_method": (
                        "percentile_plus_daily_anomaly"
                    ),
                },
            )
        )

    return candidatos


def detectar_cold_wave_candidates(
    registros: list[dict[str, Any]],
    baseline_localidade: dict[str, Any],
    regra: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """
    Detecta candidatos a onda de frio.

    Um dia somente participa da sequência quando
    satisfaz simultaneamente:

    - Tmin abaixo do percentil configurado;
    - anomalia suficientemente negativa em
      relação à média climatológica mensal.

    A sequência precisa possuir ao menos
    minimum_consecutive_days.
    """
    if regra.get(
        "enabled"
    ) is not True:
        return []

    dias_aprovados: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ] = []

    for registro in registros:
        detalhe = (
            avaliar_regra_percentil(
                registro=registro,
                baseline_localidade=(
                    baseline_localidade
                ),
                regra=regra,
            )
        )

        if detalhe is not None:
            dias_aprovados.append(
                (
                    registro,
                    detalhe,
                )
            )

    minimo_dias = int(
        regra[
            "minimum_consecutive_days"
        ]
    )

    candidatos: list[
        EventCandidate
    ] = []

    sequencias = (
        separar_sequencias_consecutivas(
            dias_aprovados
        )
    )

    for sequencia in sequencias:
        if len(
            sequencia
        ) < minimo_dias:
            continue

        registros_sequencia = [
            item[0]
            for item in sequencia
        ]

        detalhes_dias = [
            item[1]
            for item in sequencia
        ]

        valores = [
            float(
                detalhe["value"]
            )
            for detalhe
            in detalhes_dias
        ]

        medias_climatologicas = [
            float(
                detalhe[
                    "climatological_mean"
                ]
            )
            for detalhe
            in detalhes_dias
        ]

        anomalias = [
            float(
                detalhe[
                    "anomaly_from_mean_c"
                ]
            )
            for detalhe
            in detalhes_dias
        ]

        temperatura_media_periodo = (
            sum(valores)
            / len(valores)
        )

        media_climatologica_periodo = (
            sum(
                medias_climatologicas
            )
            / len(
                medias_climatologicas
            )
        )

        anomalia_media_periodo = (
            sum(anomalias)
            / len(anomalias)
        )

        anomalia_minima = min(
            anomalias
        )

        cidade = str(
            registros_sequencia[
                0
            ][
                "location_name"
            ]
        )

        data_inicial = str(
            registros_sequencia[
                0
            ][
                "date_local"
            ]
        )

        data_final = str(
            registros_sequencia[
                -1
            ][
                "date_local"
            ]
        )

        summary = (
            f"Candidato a onda de frio "
            f"em {cidade} entre "
            f"{data_inicial} e "
            f"{data_final}: "
            f"{len(registros_sequencia)} "
            "dias consecutivos satisfazendo "
            f"{regra['percentile']} e "
            "anomalia máxima permitida de "
            f"{float(regra['anomaly_threshold_c']):+.1f} °C. "
            "A média das mínimas do período "
            f"foi {temperatura_media_periodo:.1f} °C, "
            "contra média climatológica de "
            f"{media_climatologica_periodo:.1f} °C, "
            "com anomalia média de "
            f"{anomalia_media_periodo:+.1f} °C."
        )

        candidatos.append(
            construir_candidato(
                event_type=(
                    "cold_wave_candidate"
                ),
                registros=(
                    registros_sequencia
                ),
                regra=regra,
                metrics={
                    "cold_days": (
                        detalhes_dias
                    ),
                    "period": {
                        "day_count": len(
                            registros_sequencia
                        ),
                        "mean_temperature_c": round(
                            temperatura_media_periodo,
                            3,
                        ),
                        "mean_climatological_temperature_c": round(
                            media_climatologica_periodo,
                            3,
                        ),
                        "mean_anomaly_c": round(
                            anomalia_media_periodo,
                            3,
                        ),
                        "minimum_anomaly_c": round(
                            anomalia_minima,
                            3,
                        ),
                    },
                },
                summary=summary,
                rules_version=(
                    rules_version
                ),
                extra_data={
                    "wave_method": (
                        "percentile_plus_daily_anomaly"
                    ),
                },
            )
        )

    return candidatos


def detectar_eventos_precipitacao(
    registros: list[dict[str, Any]],
    regras: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """Detecta chuva intensa ou extrema sem duplicar faixas."""
    candidatos: list[EventCandidate] = []

    for registro in registros:
        event_type: str | None = None
        detalhe = avaliar_regra_absoluta(
            registro,
            regras["extreme_rain_day"],
        )

        if detalhe is not None:
            event_type = "extreme_rain_day"
        else:
            detalhe = avaliar_regra_absoluta(
                registro,
                regras["heavy_rain_day"],
            )

            if detalhe is not None:
                event_type = "heavy_rain_day"

        if event_type is None or detalhe is None:
            continue

        cidade = str(registro["location_name"])

        candidatos.append(
            construir_candidato(
                event_type=event_type,
                registros=[registro],
                regra=regras[event_type],
                metrics={"primary": detalhe},
                summary=construir_resumo_absoluto(
                    event_type,
                    cidade,
                    detalhe,
                ),
                rules_version=rules_version,
            )
        )

    return candidatos


def detectar_eventos_vento(
    registros: list[dict[str, Any]],
    regras: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """Detecta a maior faixa de rajada atingida por dia."""
    candidatos: list[EventCandidate] = []

    ordem = (
        "extreme_wind_day",
        "severe_wind_day",
        "strong_wind_day",
    )

    for registro in registros:
        event_type: str | None = None
        detalhe: dict[str, Any] | None = None

        for nome_regra in ordem:
            avaliacao = avaliar_regra_absoluta(
                registro,
                regras[nome_regra],
            )

            if avaliacao is not None:
                event_type = nome_regra
                detalhe = avaliacao
                break

        if event_type is None or detalhe is None:
            continue

        cidade = str(registro["location_name"])

        candidatos.append(
            construir_candidato(
                event_type=event_type,
                registros=[registro],
                regra=regras[event_type],
                metrics={"primary": detalhe},
                summary=construir_resumo_absoluto(
                    event_type,
                    cidade,
                    detalhe,
                ),
                rules_version=rules_version,
            )
        )

    return candidatos


def detectar_tempestades(
    registros: list[dict[str, Any]],
    regra: dict[str, Any],
    rules_version: str,
) -> list[EventCandidate]:
    """Detecta candidatos a tempestade por código ou composição diária."""
    if regra.get("enabled") is not True:
        return []

    codigos = {
        int(valor)
        for valor in regra["forecast_weather_codes"]
    }
    precipitacao_minima = float(
        regra["minimum_precipitation_mm"]
    )
    rajada_minima = float(
        regra["minimum_wind_gust_kmh"]
    )
    usar_codigo_so_previsao = bool(
        regra.get("use_weather_code_only_for_forecast", True)
    )

    candidatos: list[EventCandidate] = []

    for registro in registros:
        weather_code_bruto = registro.get("weather_code")
        precipitacao_bruta = registro.get("precipitation_sum")
        rajada_bruta = registro.get("wind_gusts_10m_max")

        weather_code = (
            int(weather_code_bruto)
            if weather_code_bruto is not None
            else None
        )
        precipitacao = (
            float(precipitacao_bruta)
            if precipitacao_bruta is not None
            else None
        )
        rajada = (
            float(rajada_bruta)
            if rajada_bruta is not None
            else None
        )

        condicoes: list[str] = []

        codigo_permitido = (
            str(registro["source_service"]) == "forecast"
            if usar_codigo_so_previsao
            else True
        )

        if (
            codigo_permitido
            and weather_code is not None
            and weather_code in codigos
        ):
            condicoes.append(
                "código meteorológico diário de tempestade "
                f"({weather_code})"
            )

        chuva_e_vento = (
            precipitacao is not None
            and rajada is not None
            and precipitacao >= precipitacao_minima
            and rajada >= rajada_minima
        )

        if chuva_e_vento:
            condicoes.append(
                "chuva e vento fortes no mesmo dia "
                f"({precipitacao:.1f} mm e {rajada:.1f} km/h)"
            )

        if not condicoes:
            continue

        detalhe = {
            "date_local": str(registro["date_local"]),
            "weather_code": weather_code,
            "precipitation_sum": precipitacao,
            "wind_gusts_10m_max": rajada,
            "minimum_precipitation_mm": precipitacao_minima,
            "minimum_wind_gust_kmh": rajada_minima,
            "forecast_weather_codes": sorted(codigos),
            "matched_conditions": condicoes,
            "temporal_resolution": str(
                regra.get("temporal_resolution", "daily")
            ),
            "simultaneity_confirmed": bool(
                regra.get("simultaneity_confirmed", False)
            ),
        }

        cidade = str(registro["location_name"])

        candidatos.append(
            construir_candidato(
                event_type="storm_candidate",
                registros=[registro],
                regra=regra,
                metrics={"compound": detalhe},
                summary=construir_resumo_absoluto(
                    "storm_candidate",
                    cidade,
                    detalhe,
                ),
                rules_version=rules_version,
                extra_data={
                    "requires_hourly_enrichment": True,
                },
            )
        )

    return candidatos


def detectar_candidatos_localidade(
    registros: list[dict[str, Any]],
    baseline_localidade: dict[str, Any],
    regras_payload: dict[str, Any],
) -> list[EventCandidate]:
    """Executa todas as famílias de detectores para uma localidade."""
    rules_version = str(regras_payload["rules_version"])

    candidatos = detectar_eventos_termicos_diarios(
        registros,
        baseline_localidade,
        regras_payload["temperature_events"],
        rules_version,
    )

    candidatos.extend(
        detectar_heat_wave_candidates(
            registros,
            baseline_localidade,
            regras_payload["temperature_events"][
                "heat_wave_candidate"
            ],
            rules_version,
        )
    )

    candidatos.extend(
        detectar_cold_wave_candidates(
            registros,
            baseline_localidade,
            regras_payload["temperature_events"][
                "cold_wave_candidate"
            ],
            rules_version,
        )
    )

    candidatos.extend(
        detectar_eventos_precipitacao(
            registros,
            regras_payload["precipitation_events"],
            rules_version,
        )
    )

    candidatos.extend(
        detectar_eventos_vento(
            registros,
            regras_payload["wind_events"],
            rules_version,
        )
    )

    candidatos.extend(
        detectar_tempestades(
            registros,
            regras_payload["storm_events"]["storm_candidate"],
            rules_version,
        )
    )

    return candidatos


def remover_candidatos_duplicados(
    candidatos: list[EventCandidate],
) -> list[EventCandidate]:
    """Remove duplicidades determinísticas por candidate_id."""
    indice: dict[str, EventCandidate] = {}

    for candidato in candidatos:
        indice[candidato.candidate_id] = candidato

    resultado = list(indice.values())

    resultado.sort(
        key=lambda item: (
            item.location_slug,
            item.start_at,
            item.event_family,
            item.event_type,
        )
    )

    return resultado


def caminho_relativo_projeto(caminho: Path) -> str:
    """Retorna um caminho relativo à raiz OpenMeteo."""
    try:
        return str(caminho.relative_to(BASE_DIR))
    except ValueError:
        return str(caminho)


def salvar_candidatos_por_localidade(
    candidatos: list[EventCandidate],
    slugs_localidades: list[str],
    rules_version: str,
) -> list[str]:
    """Salva um arquivo por localidade, inclusive quando vazio."""
    grupos: dict[str, list[EventCandidate]] = {
        slug: []
        for slug in slugs_localidades
    }

    for candidato in candidatos:
        grupos.setdefault(candidato.location_slug, []).append(candidato)

    arquivos: list[str] = []

    for slug in sorted(grupos):
        grupo = grupos[slug]
        grupo.sort(
            key=lambda item: (
                item.start_at,
                item.event_family,
                item.event_type,
            )
        )

        caminho = (
            STAGING_EVENTS_DIR
            / f"{slug}__weather_event_candidates.json"
        )

        payload = {
            "schema_version": "1.0",
            "detector_version": WEATHER_DETECTOR_VERSION,
            "rules_version": rules_version,
            "generated_at_utc": agora_utc_iso(),
            "location_slug": slug,
            "candidate_count": len(grupo),
            "candidate_count_by_type": dict(
                sorted(Counter(item.event_type for item in grupo).items())
            ),
            "candidates": [
                candidato.to_dict()
                for candidato in grupo
            ],
        }

        salvar_json(caminho, payload)
        arquivos.append(caminho_relativo_projeto(caminho))

    return arquivos


def detectar_eventos_climaticos() -> dict[str, Any]:
    """Executa todos os detectores e salva candidatos e manifesto."""
    regras_payload = carregar_regras_clima()
    registros = carregar_registros_diarios()
    baselines = carregar_indice_baseline()
    grupos = agrupar_registros_por_localidade(registros)

    rules_version = str(regras_payload["rules_version"])
    candidatos: list[EventCandidate] = []

    for location_slug, registros_localidade in sorted(grupos.items()):
        baseline_localidade = baselines.get(location_slug)

        if baseline_localidade is None:
            raise ValueError(
                "Baseline não encontrada para a localidade: "
                f"{location_slug}"
            )

        candidatos_localidade = detectar_candidatos_localidade(
            registros=registros_localidade,
            baseline_localidade=baseline_localidade,
            regras_payload=regras_payload,
        )

        logging.info(
            "%s candidatos climáticos detectados em %s.",
            len(candidatos_localidade),
            location_slug,
        )

        candidatos.extend(candidatos_localidade)

    candidatos = remover_candidatos_duplicados(candidatos)

    contagem_por_tipo = Counter(
        candidato.event_type
        for candidato in candidatos
    )
    contagem_por_familia = Counter(
        candidato.event_family
        for candidato in candidatos
    )
    contagem_por_severidade = Counter(
        candidato.severity
        for candidato in candidatos
    )
    contagem_por_localidade = Counter(
        candidato.location_slug
        for candidato in candidatos
    )

    payload_candidatos = {
        "schema_version": "1.0",
        "detector_version": WEATHER_DETECTOR_VERSION,
        "rules_version": rules_version,
        "generated_at_utc": agora_utc_iso(),
        "candidate_count": len(candidatos),
        "candidate_count_by_type": dict(
            sorted(contagem_por_tipo.items())
        ),
        "candidate_count_by_family": dict(
            sorted(contagem_por_familia.items())
        ),
        "candidate_count_by_severity": dict(
            sorted(contagem_por_severidade.items())
        ),
        "candidate_count_by_location": dict(
            sorted(contagem_por_localidade.items())
        ),
        "candidates": [
            candidato.to_dict()
            for candidato in candidatos
        ],
    }

    salvar_json(
        WEATHER_EVENT_CANDIDATES_PATH,
        payload_candidatos,
    )
    
    arquivos_resumo = (
    salvar_relatorio_climatico(
        candidatos=candidatos,
        rules_version=rules_version,
    )
)

    arquivos_localidade = salvar_candidatos_por_localidade(
        candidatos=candidatos,
        slugs_localidades=sorted(grupos),
        rules_version=rules_version,
    )

    manifesto = {
        "schema_version": "1.0",
        "detector_version": WEATHER_DETECTOR_VERSION,
        "rules_version": rules_version,
        "generated_at_utc": agora_utc_iso(),
        "daily_record_count": len(registros),
        "location_count": len(grupos),
        "candidate_count": len(candidatos),
        "candidate_count_by_type": dict(
            sorted(contagem_por_tipo.items())
        ),
        "candidate_count_by_family": dict(
            sorted(contagem_por_familia.items())
        ),
        "candidate_count_by_severity": dict(
            sorted(contagem_por_severidade.items())
        ),
        "candidate_count_by_location": dict(
            sorted(contagem_por_localidade.items())
        ),
        "candidates_file": caminho_relativo_projeto(
            WEATHER_EVENT_CANDIDATES_PATH
        ),
        "summary_json_file": (
            caminho_relativo_projeto(
                WEATHER_EVENT_SUMMARY_JSON_PATH
            )
        ), 

        "summary_csv_file": (
            caminho_relativo_projeto(
                WEATHER_EVENT_SUMMARY_CSV_PATH
            )
        ),

        "summary_txt_file": (
            caminho_relativo_projeto(
                WEATHER_EVENT_SUMMARY_TXT_PATH
            )
        ),


        "location_files": arquivos_localidade,
    }

    salvar_json(
        WEATHER_EVENT_CANDIDATES_MANIFEST_PATH,
        manifesto,
    )

    logging.info(
        "Candidatos climáticos salvos em: %s.",
        WEATHER_EVENT_CANDIDATES_PATH,
    )

    return manifesto
