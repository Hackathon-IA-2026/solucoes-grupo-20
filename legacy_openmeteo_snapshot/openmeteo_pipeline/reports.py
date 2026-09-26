from __future__ import annotations

import csv
from statistics import mean
from typing import Any

from openmeteo_pipeline.config import (
    WEATHER_EVENT_SUMMARY_CSV_PATH,
    WEATHER_EVENT_SUMMARY_JSON_PATH,
    WEATHER_EVENT_SUMMARY_TXT_PATH,
)
from openmeteo_pipeline.models import (
    EventCandidate,
)
from openmeteo_pipeline.storage import (
    agora_utc_iso,
    salvar_json,
)


def unidade_metrica(
    metrica: str | None,
    detalhe: dict[str, Any],
) -> str:
    """
    Determina a unidade usada na apresentação.
    """
    unidade = detalhe.get("unit")

    if isinstance(unidade, str):
        return unidade.replace(
            "/day",
            "",
        )

    if metrica in {
        "temperature_2m_max",
        "temperature_2m_min",
    }:
        return "°C"

    if metrica == "precipitation_sum":
        return "mm"

    if metrica == "wind_gusts_10m_max":
        return "km/h"

    return ""


def formatar_numero(
    valor: Any,
) -> str:
    if isinstance(
        valor,
        (int, float),
    ):
        return f"{float(valor):.1f}"

    return str(valor)


def construir_criterio_primario(
    detalhe: dict[str, Any],
) -> str:
    """
    Constrói a descrição numérica de um evento
    diário.

    Para eventos térmicos do Detector 1.2,
    apresenta:

    - valor observado ou previsto;
    - média climatológica;
    - anomalia;
    - percentil;
    - limiar de anomalia, quando aplicável.

    Para chuva e vento mantém a lógica de
    limiar absoluto.
    """
    metrica = detalhe.get(
        "metric"
    )

    valor = detalhe.get(
        "value"
    )

    limiar = detalhe.get(
        "threshold_value"
    )

    unidade = unidade_metrica(
        str(metrica)
        if metrica is not None
        else None,
        detalhe,
    )

    percentil = detalhe.get(
        "percentile"
    )

    operador = detalhe.get(
        "operator"
    )

    simbolo = {
        "greater_than_or_equal": ">=",
        "less_than_or_equal": "<=",
        "greater_than": ">",
        "less_than": "<",
    }.get(
        str(operador),
        str(operador),
    )

    partes: list[str] = []

    # ---------------------------------------------------------
    # VALOR PRINCIPAL
    # ---------------------------------------------------------

    if percentil is not None:
        partes.append(
            (
                f"{metrica}: "
                f"{formatar_numero(valor)} "
                f"{unidade} "
                f"{simbolo} "
                f"{percentil}="
                f"{formatar_numero(limiar)} "
                f"{unidade}"
            ).strip()
        )

    else:
        partes.append(
            (
                f"{metrica}: "
                f"{formatar_numero(valor)} "
                f"{unidade} "
                f"{simbolo} "
                "limiar "
                f"{formatar_numero(limiar)} "
                f"{unidade}"
            ).strip()
        )

    # ---------------------------------------------------------
    # MÉDIA CLIMATOLÓGICA
    # ---------------------------------------------------------

    media_climatologica = detalhe.get(
        "climatological_mean"
    )

    anomalia = detalhe.get(
        "anomaly_from_mean_c"
    )

    if isinstance(
        media_climatologica,
        (int, float),
    ):
        partes.append(
            (
                "média climatológica: "
                f"{float(media_climatologica):.1f} °C"
            )
        )

    if isinstance(
        anomalia,
        (int, float),
    ):
        partes.append(
            (
                "anomalia: "
                f"{float(anomalia):+.1f} °C"
            )
        )

    # ---------------------------------------------------------
    # LIMIAR DE MAGNITUDE
    # ---------------------------------------------------------

    anomaly_threshold = detalhe.get(
        "anomaly_threshold_c"
    )

    anomaly_operator = detalhe.get(
        "anomaly_operator"
    )

    if (
        isinstance(
            anomaly_threshold,
            (int, float),
        )
        and anomaly_operator is not None
    ):
        simbolo_anomalia = {
            "greater_than_or_equal": ">=",
            "less_than_or_equal": "<=",
            "greater_than": ">",
            "less_than": "<",
        }.get(
            str(anomaly_operator),
            str(anomaly_operator),
        )

        partes.append(
            (
                "critério de anomalia: "
                f"{float(anomalia):+.1f} °C "
                f"{simbolo_anomalia} "
                f"{float(anomaly_threshold):+.1f} °C"
            )
        )

    return "; ".join(
        partes
    )


def construir_criterio_onda_calor(
    candidato: EventCandidate,
) -> str:
    """
    Constrói a descrição numérica de um
    candidato a onda de calor do Detector 1.2.
    """
    dias = candidato.metrics.get(
        "hot_days",
        [],
    )

    noites = candidato.metrics.get(
        "warm_nights",
        [],
    )

    periodo = candidato.metrics.get(
        "period",
        {},
    )

    if not isinstance(
        dias,
        list,
    ):
        dias = []

    if not isinstance(
        noites,
        list,
    ):
        noites = []

    if not isinstance(
        periodo,
        dict,
    ):
        periodo = {}

    valores = [
        float(
            item["value"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "value"
        ) is not None
    ]

    limiares = [
        float(
            item["threshold_value"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "threshold_value"
        ) is not None
    ]

    medias = [
        float(
            item["climatological_mean"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "climatological_mean"
        ) is not None
    ]

    anomalias = [
        float(
            item["anomaly_from_mean_c"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "anomaly_from_mean_c"
        ) is not None
    ]

    partes: list[str] = []

    partes.append(
        f"{len(dias)} dias consecutivos"
    )

    if valores:
        partes.append(
            (
                "máximas: "
                + ", ".join(
                    f"{valor:.1f}"
                    for valor in valores
                )
                + " °C"
            )
        )

    media_periodo = periodo.get(
        "mean_temperature_c"
    )

    if isinstance(
        media_periodo,
        (int, float),
    ):
        partes.append(
            (
                "média das máximas: "
                f"{float(media_periodo):.1f} °C"
            )
        )

    elif valores:
        partes.append(
            (
                "média das máximas: "
                f"{mean(valores):.1f} °C"
            )
        )

    media_climatologica_periodo = (
        periodo.get(
            "mean_climatological_temperature_c"
        )
    )

    if isinstance(
        media_climatologica_periodo,
        (int, float),
    ):
        partes.append(
            (
                "média climatológica do período: "
                f"{float(media_climatologica_periodo):.1f} °C"
            )
        )

    elif medias:
        partes.append(
            (
                "média climatológica do período: "
                f"{mean(medias):.1f} °C"
            )
        )

    anomalia_media = periodo.get(
        "mean_anomaly_c"
    )

    if isinstance(
        anomalia_media,
        (int, float),
    ):
        partes.append(
            (
                "anomalia média: "
                f"{float(anomalia_media):+.1f} °C"
            )
        )

    elif anomalias:
        partes.append(
            (
                "anomalia média: "
                f"{mean(anomalias):+.1f} °C"
            )
        )

    anomalia_maxima = periodo.get(
        "maximum_anomaly_c"
    )

    if isinstance(
        anomalia_maxima,
        (int, float),
    ):
        partes.append(
            (
                "maior anomalia: "
                f"{float(anomalia_maxima):+.1f} °C"
            )
        )

    percentil = candidato.rule.get(
        "percentile"
    )

    anomaly_threshold = (
        candidato.rule.get(
            "anomaly_threshold_c"
        )
    )

    if (
        percentil is not None
        and anomaly_threshold is not None
    ):
        partes.append(
            (
                "critério diário: "
                f"Tmax >= {percentil} "
                "e anomalia >= "
                f"{float(anomaly_threshold):+.1f} °C"
            )
        )

    if limiares:
        partes.append(
            (
                f"limiares {percentil}: "
                + ", ".join(
                    f"{valor:.1f}"
                    for valor in limiares
                )
                + " °C"
            )
        )

    if noites:
        partes.append(
            (
                "noites quentes: "
                f"{len(noites)}/{len(dias)}"
            )
        )

    return "; ".join(
        partes
    )


def construir_criterio_onda_frio(
    candidato: EventCandidate,
) -> str:
    """
    Constrói a descrição numérica de um
    candidato a onda de frio do Detector 1.2.
    """
    dias = candidato.metrics.get(
        "cold_days",
        [],
    )

    periodo = candidato.metrics.get(
        "period",
        {},
    )

    if not isinstance(
        dias,
        list,
    ):
        dias = []

    if not isinstance(
        periodo,
        dict,
    ):
        periodo = {}

    valores = [
        float(
            item["value"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "value"
        ) is not None
    ]

    limiares = [
        float(
            item["threshold_value"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "threshold_value"
        ) is not None
    ]

    medias = [
        float(
            item["climatological_mean"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "climatological_mean"
        ) is not None
    ]

    anomalias = [
        float(
            item["anomaly_from_mean_c"]
        )
        for item in dias
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "anomaly_from_mean_c"
        ) is not None
    ]

    partes: list[str] = []

    partes.append(
        f"{len(dias)} dias consecutivos"
    )

    if valores:
        partes.append(
            (
                "mínimas: "
                + ", ".join(
                    f"{valor:.1f}"
                    for valor in valores
                )
                + " °C"
            )
        )

    media_periodo = periodo.get(
        "mean_temperature_c"
    )

    if isinstance(
        media_periodo,
        (int, float),
    ):
        partes.append(
            (
                "média das mínimas: "
                f"{float(media_periodo):.1f} °C"
            )
        )

    elif valores:
        partes.append(
            (
                "média das mínimas: "
                f"{mean(valores):.1f} °C"
            )
        )

    media_climatologica_periodo = (
        periodo.get(
            "mean_climatological_temperature_c"
        )
    )

    if isinstance(
        media_climatologica_periodo,
        (int, float),
    ):
        partes.append(
            (
                "média climatológica do período: "
                f"{float(media_climatologica_periodo):.1f} °C"
            )
        )

    elif medias:
        partes.append(
            (
                "média climatológica do período: "
                f"{mean(medias):.1f} °C"
            )
        )

    anomalia_media = periodo.get(
        "mean_anomaly_c"
    )

    if isinstance(
        anomalia_media,
        (int, float),
    ):
        partes.append(
            (
                "anomalia média: "
                f"{float(anomalia_media):+.1f} °C"
            )
        )

    elif anomalias:
        partes.append(
            (
                "anomalia média: "
                f"{mean(anomalias):+.1f} °C"
            )
        )

    anomalia_minima = periodo.get(
        "minimum_anomaly_c"
    )

    if isinstance(
        anomalia_minima,
        (int, float),
    ):
        partes.append(
            (
                "menor anomalia: "
                f"{float(anomalia_minima):+.1f} °C"
            )
        )

    percentil = candidato.rule.get(
        "percentile"
    )

    anomaly_threshold = (
        candidato.rule.get(
            "anomaly_threshold_c"
        )
    )

    if (
        percentil is not None
        and anomaly_threshold is not None
    ):
        partes.append(
            (
                "critério diário: "
                f"Tmin <= {percentil} "
                "e anomalia <= "
                f"{float(anomaly_threshold):+.1f} °C"
            )
        )

    if limiares:
        partes.append(
            (
                f"limiares {percentil}: "
                + ", ".join(
                    f"{valor:.1f}"
                    for valor in limiares
                )
                + " °C"
            )
        )

    return "; ".join(
        partes
    )


def construir_criterio_tempestade(
    candidato: EventCandidate,
) -> str:
    detalhe = candidato.metrics.get(
        "compound",
        {},
    )

    partes: list[str] = []

    weather_code = detalhe.get(
        "weather_code"
    )

    codigos = detalhe.get(
        "forecast_weather_codes",
        [],
    )

    if (
        weather_code is not None
        and weather_code in codigos
    ):
        partes.append(
            f"WMO code {weather_code} "
            f"em {codigos}"
        )

    precipitacao = detalhe.get(
        "precipitation_sum"
    )

    minimo_chuva = detalhe.get(
        "minimum_precipitation_mm"
    )

    if precipitacao is not None:
        partes.append(
            "chuva: "
            f"{float(precipitacao):.1f} mm "
            f"(limiar "
            f"{float(minimo_chuva):.1f} mm)"
        )

    rajada = detalhe.get(
        "wind_gusts_10m_max"
    )

    minimo_rajada = detalhe.get(
        "minimum_wind_gust_kmh"
    )

    if rajada is not None:
        partes.append(
            "rajada: "
            f"{float(rajada):.1f} km/h "
            f"(limiar "
            f"{float(minimo_rajada):.1f} km/h)"
        )

    return "; ".join(partes)


def construir_criterio_numerico(
    candidato: EventCandidate,
) -> str:
    if candidato.event_type == (
        "heat_wave_candidate"
    ):
        return construir_criterio_onda_calor(
            candidato
        )

    if candidato.event_type == (
        "cold_wave_candidate"
    ):
        return construir_criterio_onda_frio(
            candidato
        )

    if candidato.event_type == (
        "storm_candidate"
    ):
        return construir_criterio_tempestade(
            candidato
        )

    detalhe = candidato.metrics.get(
        "primary"
    )

    if isinstance(detalhe, dict):
        return construir_criterio_primario(
            detalhe
        )

    return candidato.summary


def obter_periodo(
    candidato: EventCandidate,
) -> tuple[str, str]:
    return (
        candidato.start_at[:10],
        candidato.end_at[:10],
    )


def construir_resumo_candidato(
    candidato: EventCandidate,
) -> dict[str, Any]:
    """
    Cria uma linha consolidada do relatório.

    Além do texto legível, expõe campos
    numéricos estruturados para facilitar
    filtragem e análise.
    """
    data_inicial, data_final = (
        obter_periodo(
            candidato
        )
    )

    valor_principal = None
    media_climatologica = None
    anomalia_c = None
    percentil = None
    limiar_percentil = None
    limiar_anomalia_c = None

    dias_consecutivos = None
    media_periodo_c = None
    media_climatologica_periodo_c = None
    anomalia_media_periodo_c = None
    anomalia_extrema_periodo_c = None

    primary = candidato.metrics.get(
        "primary"
    )

    if isinstance(
        primary,
        dict,
    ):
        valor_principal = primary.get(
            "value"
        )

        media_climatologica = (
            primary.get(
                "climatological_mean"
            )
        )

        anomalia_c = primary.get(
            "anomaly_from_mean_c"
        )

        percentil = primary.get(
            "percentile"
        )

        limiar_percentil = primary.get(
            "threshold_value"
        )

        limiar_anomalia_c = primary.get(
            "anomaly_threshold_c"
        )

    period = candidato.metrics.get(
        "period"
    )

    if isinstance(
        period,
        dict,
    ):
        dias_consecutivos = period.get(
            "day_count"
        )

        media_periodo_c = period.get(
            "mean_temperature_c"
        )

        media_climatologica_periodo_c = (
            period.get(
                "mean_climatological_temperature_c"
            )
        )

        anomalia_media_periodo_c = (
            period.get(
                "mean_anomaly_c"
            )
        )

        if candidato.event_family == "heat":
            anomalia_extrema_periodo_c = (
                period.get(
                    "maximum_anomaly_c"
                )
            )

        elif candidato.event_family == "cold":
            anomalia_extrema_periodo_c = (
                period.get(
                    "minimum_anomaly_c"
                )
            )

    return {
        "candidate_id": (
            candidato.candidate_id
        ),
        "data_inicio": (
            data_inicial
        ),
        "data_fim": (
            data_final
        ),
        "cidade": (
            candidato.city_name
        ),
        "uf": (
            candidato.state_code
        ),
        "status": (
            candidato.status
        ),
        "event_type": (
            candidato.event_type
        ),
        "event_family": (
            candidato.event_family
        ),
        "severity": (
            candidato.severity
        ),
        "titulo": (
            candidato.title
        ),

        "valor_principal": (
            valor_principal
        ),
        "media_climatologica": (
            media_climatologica
        ),
        "anomalia_c": (
            anomalia_c
        ),
        "percentil": (
            percentil
        ),
        "limiar_percentil": (
            limiar_percentil
        ),
        "limiar_anomalia_c": (
            limiar_anomalia_c
        ),

        "dias_consecutivos": (
            dias_consecutivos
        ),
        "media_periodo_c": (
            media_periodo_c
        ),
        "media_climatologica_periodo_c": (
            media_climatologica_periodo_c
        ),
        "anomalia_media_periodo_c": (
            anomalia_media_periodo_c
        ),
        "anomalia_extrema_periodo_c": (
            anomalia_extrema_periodo_c
        ),

        "criterio_numerico": (
            construir_criterio_numerico(
                candidato
            )
        ),
        "resumo": (
            candidato.summary
        ),
    }


def status_legivel(
    status: str,
) -> str:
    return {
        "forecast": "PREVISTO",
        "historical_reanalysis": (
            "HISTÓRICO"
        ),
        "provisional": "PROVISÓRIO",
        "mixed": "MISTO",
    }.get(
        status,
        status.upper(),
    )


def salvar_relatorio_climatico(
    candidatos: list[EventCandidate],
    rules_version: str,
) -> dict[str, str]:
    """
    Gera os relatórios consolidados dos
    candidatos climáticos:

    - JSON estruturado;
    - CSV para consulta tabular;
    - TXT para leitura rápida.
    """
    linhas = [
        construir_resumo_candidato(
            candidato
        )
        for candidato in candidatos
    ]

    linhas.sort(
        key=lambda item: (
            item["data_inicio"],
            item["uf"] or "",
            item["cidade"],
            item["event_type"],
        )
    )

    payload = {
        "schema_version": "1.1",
        "rules_version": (
            rules_version
        ),
        "generated_at_utc": (
            agora_utc_iso()
        ),
        "candidate_count": (
            len(linhas)
        ),
        "candidates": (
            linhas
        ),
    }

    salvar_json(
        WEATHER_EVENT_SUMMARY_JSON_PATH,
        payload,
    )

    WEATHER_EVENT_SUMMARY_CSV_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    campos_csv = [
        "data_inicio",
        "data_fim",
        "cidade",
        "uf",
        "status",
        "event_type",
        "event_family",
        "severity",
        "titulo",

        "valor_principal",
        "media_climatologica",
        "anomalia_c",
        "percentil",
        "limiar_percentil",
        "limiar_anomalia_c",

        "dias_consecutivos",
        "media_periodo_c",
        "media_climatologica_periodo_c",
        "anomalia_media_periodo_c",
        "anomalia_extrema_periodo_c",

        "criterio_numerico",
        "resumo",
        "candidate_id",
    ]

    with (
        WEATHER_EVENT_SUMMARY_CSV_PATH.open(
            "w",
            encoding="utf-8",
            newline="",
        )
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=campos_csv,
            delimiter=";",
        )

        escritor.writeheader()

        for linha in linhas:
            escritor.writerow(
                linha
            )

    # ---------------------------------------------------------
    # TXT PARA CONSULTA HUMANA
    # ---------------------------------------------------------

    blocos_txt: list[str] = []

    for linha in linhas:
        if (
            linha["data_inicio"]
            == linha["data_fim"]
        ):
            periodo = linha[
                "data_inicio"
            ]

        else:
            periodo = (
                f"{linha['data_inicio']} "
                f"a {linha['data_fim']}"
            )

        local = linha[
            "cidade"
        ]

        if linha["uf"]:
            local += (
                f"/{linha['uf']}"
            )

        cabecalho = (
            f"{periodo} | "
            f"{local} | "
            f"{status_legivel(linha['status'])}"
        )

        titulo = (
            f"{linha['titulo']} | "
            f"{linha['severity']}"
        )

        bloco = [
            cabecalho,
            titulo,
            linha[
                "criterio_numerico"
            ],
            "",
        ]

        blocos_txt.append(
            "\n".join(
                bloco
            )
        )

    WEATHER_EVENT_SUMMARY_TXT_PATH.write_text(
        "\n".join(
            blocos_txt
        ),
        encoding="utf-8",
    )

    return {
        "json_file": str(
            WEATHER_EVENT_SUMMARY_JSON_PATH
        ),
        "csv_file": str(
            WEATHER_EVENT_SUMMARY_CSV_PATH
        ),
        "txt_file": str(
            WEATHER_EVENT_SUMMARY_TXT_PATH
        ),
    }