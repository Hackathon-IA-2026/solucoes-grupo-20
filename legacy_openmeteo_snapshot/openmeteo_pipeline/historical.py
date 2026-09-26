from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from openmeteo_pipeline.client import obter_json
from openmeteo_pipeline.collector import (
    carregar_localidades_resolvidas,
)
from openmeteo_pipeline.config import (
    BASE_DIR,
    HISTORICAL_DAILY_VARIABLES,
    HISTORICAL_DAYS,
    HISTORICAL_MANIFEST_PATH,
    OPENMETEO_HISTORICAL_URL,
    RAW_HISTORICAL_DIR,
)
from openmeteo_pipeline.storage import (
    agora_utc_iso,
    persistir_raw_external_record,
    salvar_json,
)


def calcular_intervalo_historico(
    localidade: dict[str, Any],
) -> tuple[str, str]:
    """
    Calcula os 14 dias locais completos anteriores
    ao dia atual.

    Exemplo:

    hoje local: 2026-08-02
    início:     2026-07-19
    fim:        2026-08-01
    """
    timezone_name = str(
        localidade["timezone"]
    )

    try:
        timezone_local = ZoneInfo(
            timezone_name
        )
    except ZoneInfoNotFoundError as erro:
        raise ValueError(
            "Timezone inválido para a localidade "
            f"{localidade['slug']}: "
            f"{timezone_name}"
        ) from erro

    hoje_local = datetime.now(
        timezone_local
    ).date()

    data_final = (
        hoje_local
        - timedelta(days=1)
    )

    data_inicial = (
        data_final
        - timedelta(
            days=HISTORICAL_DAYS - 1
        )
    )

    return (
        data_inicial.isoformat(),
        data_final.isoformat(),
    )


def criar_parametros_historico(
    localidade: dict[str, Any],
    data_inicial: str,
    data_final: str,
) -> dict[str, Any]:
    """
    Cria os parâmetros da Historical Weather API.
    """
    return {
        "latitude": float(
            localidade["latitude"]
        ),
        "longitude": float(
            localidade["longitude"]
        ),
        "timezone": str(
            localidade["timezone"]
        ),
        "start_date": data_inicial,
        "end_date": data_final,
        "daily": ",".join(
            HISTORICAL_DAILY_VARIABLES
        ),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timeformat": "iso8601",
    }


def validar_series_mesmo_tamanho(
    bloco: dict[str, Any],
    nome_bloco: str,
) -> int:
    """
    Confirma que todas as séries diárias possuem
    a mesma quantidade de posições.
    """
    tempos = bloco.get("time")

    if not isinstance(tempos, list):
        raise ValueError(
            f"O bloco '{nome_bloco}' não contém "
            "uma lista em 'time'."
        )

    quantidade = len(tempos)

    if quantidade == 0:
        raise ValueError(
            f"O bloco '{nome_bloco}' está vazio."
        )

    for campo, valores in bloco.items():
        if campo == "time":
            continue

        if not isinstance(valores, list):
            raise ValueError(
                f"O campo '{nome_bloco}.{campo}' "
                "não contém uma lista."
            )

        if len(valores) != quantidade:
            raise ValueError(
                f"O campo '{nome_bloco}.{campo}' "
                f"possui {len(valores)} valores, "
                f"mas 'time' possui {quantidade}."
            )

    return quantidade


def validar_payload_historico(
    payload: dict[str, Any],
) -> int:
    """
    Valida a estrutura diária da resposta histórica.
    """
    bloco_daily = payload.get("daily")

    if not isinstance(bloco_daily, dict):
        raise ValueError(
            "O histórico não contém um objeto "
            "no campo 'daily'."
        )

    quantidade_dias = (
        validar_series_mesmo_tamanho(
            bloco_daily,
            "daily",
        )
    )

    if quantidade_dias != HISTORICAL_DAYS:
        logging.warning(
            (
                "A API retornou %s dias históricos, "
                "embora %s tenham sido solicitados."
            ),
            quantidade_dias,
            HISTORICAL_DAYS,
        )

    return quantidade_dias


def obter_periodo_historico(
    payload: dict[str, Any],
) -> tuple[str, str]:
    """
    Obtém a primeira e a última data efetivamente
    retornadas pela API.
    """
    bloco_daily = payload["daily"]
    datas = bloco_daily["time"]

    return (
        str(datas[0]),
        str(datas[-1]),
    )


def caminho_relativo_projeto(
    caminho: Path,
) -> str:
    """
    Retorna o caminho relativo à raiz do projeto
    OpenMeteo.
    """
    try:
        return str(
            caminho.relative_to(BASE_DIR)
        )
    except ValueError:
        return str(caminho)


def coletar_historico_localidade(
    localidade: dict[str, Any],
) -> dict[str, Any]:
    """
    Coleta e preserva os 14 dias históricos de uma
    localidade.
    """
    slug = str(localidade["slug"])

    (
        data_inicial_solicitada,
        data_final_solicitada,
    ) = calcular_intervalo_historico(
        localidade
    )

    parametros = criar_parametros_historico(
        localidade=localidade,
        data_inicial=data_inicial_solicitada,
        data_final=data_final_solicitada,
    )

    logging.info(
        (
            "Coletando histórico: %s | "
            "%s até %s."
        ),
        slug,
        data_inicial_solicitada,
        data_final_solicitada,
    )

    retrieved_at_utc = agora_utc_iso()

    status_http, payload = obter_json(
        OPENMETEO_HISTORICAL_URL,
        parametros,
    )

    quantidade_dias = validar_payload_historico(
        payload
    )

    (
        data_inicial_retornada,
        data_final_retornada,
    ) = obter_periodo_historico(
        payload
    )

    external_id = (
        f"historical:{slug}:"
        f"{data_inicial_retornada}:"
        f"{data_final_retornada}"
    )

    (
        caminho_raw,
        novo_registro,
        payload_hash,
    ) = persistir_raw_external_record(
        diretorio=RAW_HISTORICAL_DIR,
        source="open-meteo",
        source_service="historical",
        source_endpoint=(
            OPENMETEO_HISTORICAL_URL
        ),
        location_slug=slug,
        external_id=external_id,
        request_parameters=parametros,
        payload=payload,
        http_status=status_http,
        retrieved_at_utc=retrieved_at_utc,
    )

    if novo_registro:
        logging.info(
            "Novo histórico RAW salvo: %s.",
            caminho_raw,
        )
    else:
        logging.info(
            (
                "Histórico idêntico já existente; "
                "nenhum novo RAW foi criado: %s."
            ),
            caminho_raw,
        )

    return {
        "location_slug": slug,
        "location_name": localidade[
            "resolved_name"
        ],
        "country_code": localidade[
            "country_code"
        ],
        "timezone": localidade[
            "timezone"
        ],
        "latitude": localidade["latitude"],
        "longitude": localidade["longitude"],
        "data_kind": (
            "historical_reanalysis"
        ),
        "data_inicial_solicitada": (
            data_inicial_solicitada
        ),
        "data_final_solicitada": (
            data_final_solicitada
        ),
        "data_inicial_retornada": (
            data_inicial_retornada
        ),
        "data_final_retornada": (
            data_final_retornada
        ),
        "quantidade_dias": quantidade_dias,
        "payload_hash": payload_hash,
        "raw_file": caminho_relativo_projeto(
            caminho_raw
        ),
        "new_raw_record": novo_registro,
        "status": "success",
    }


def coletar_clima_historico(
) -> dict[str, Any]:
    """
    Coleta os históricos de todas as localidades.

    Uma falha individual não interrompe a coleta das
    demais localidades.
    """
    localidades = (
        carregar_localidades_resolvidas()
    )

    resultados: list[dict[str, Any]] = []
    erros: list[dict[str, Any]] = []

    for localidade in localidades:
        slug = str(
            localidade.get(
                "slug",
                "localidade-desconhecida",
            )
        )

        try:
            resultado = (
                coletar_historico_localidade(
                    localidade
                )
            )

            resultados.append(resultado)

        except (
            requests.RequestException,
            ValueError,
            TypeError,
            KeyError,
            OSError,
        ) as erro:
            logging.exception(
                (
                    "Falha ao coletar histórico "
                    "de %s: %s"
                ),
                slug,
                erro,
            )

            erros.append(
                {
                    "location_slug": slug,
                    "status": "error",
                    "error_type": type(
                        erro
                    ).__name__,
                    "error_message": str(erro),
                }
            )

    if not resultados:
        raise RuntimeError(
            "Nenhum histórico foi coletado "
            "com sucesso."
        )

    manifest = {
        "schema_version": "1.0",
        "source": "open-meteo",
        "source_service": "historical",
        "data_kind": "historical_reanalysis",
        "generated_at_utc": agora_utc_iso(),
        "requested_location_count": len(
            localidades
        ),
        "success_count": len(resultados),
        "error_count": len(erros),
        "results": resultados,
        "errors": erros,
    }

    salvar_json(
        HISTORICAL_MANIFEST_PATH,
        manifest,
    )

    logging.info(
        "Manifesto histórico salvo em: %s.",
        HISTORICAL_MANIFEST_PATH,
    )

    return manifest