from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from openmeteo_pipeline.config import (
    BASE_DIR,
    DAILY_PARSER_VERSION,
    EXPECTED_DAILY_RECORDS_PER_LOCATION,
    FORECAST_MANIFEST_PATH,
    HISTORICAL_MANIFEST_PATH,
    HISTORICAL_PROVISIONAL_DAYS,
    HISTORICAL_REANALYSIS_DAYS,
    STAGING_DAILY_CONSOLIDATED_PATH,
    STAGING_DAILY_DIR,
    STAGING_DAILY_MANIFEST_PATH,
    STAGING_LOCATIONS_PATH,
)
from openmeteo_pipeline.models import (
    DailyWeatherRecord,
)
from openmeteo_pipeline.storage import (
    agora_utc_iso,
    salvar_json,
)


def carregar_json_objeto(
    caminho: Path,
) -> dict[str, Any]:
    """
    Carrega um arquivo JSON que deve conter um objeto.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    with caminho.open(
        "r",
        encoding="utf-8",
    ) as arquivo:
        payload = json.load(arquivo)

    if not isinstance(payload, dict):
        raise ValueError(
            "O arquivo deveria conter um objeto JSON: "
            f"{caminho}"
        )

    return payload


def resolver_caminho_projeto(
    caminho_informado: str,
) -> Path:
    """
    Resolve caminhos absolutos ou relativos à raiz
    do projeto OpenMeteo.
    """
    caminho = Path(caminho_informado)

    if caminho.is_absolute():
        return caminho

    return BASE_DIR / caminho


def carregar_indice_localidades(
) -> dict[str, dict[str, Any]]:
    """
    Carrega as localidades resolvidas e cria um índice
    pelo slug.
    """
    payload = carregar_json_objeto(
        STAGING_LOCATIONS_PATH
    )

    localidades = payload.get("locations")

    if not isinstance(localidades, list):
        raise ValueError(
            "locations_resolved.json não contém "
            "uma lista em 'locations'."
        )

    indice: dict[str, dict[str, Any]] = {}

    for posicao, localidade in enumerate(
        localidades,
        start=1,
    ):
        if not isinstance(localidade, dict):
            raise ValueError(
                "Localidade inválida na posição "
                f"{posicao}."
            )

        slug = localidade.get("slug")

        if not isinstance(slug, str):
            raise ValueError(
                "Localidade sem slug válido na posição "
                f"{posicao}."
            )

        if slug in indice:
            raise ValueError(
                f"Slug de localidade duplicado: {slug}"
            )

        indice[slug] = localidade

    if not indice:
        raise ValueError(
            "Nenhuma localidade resolvida foi encontrada."
        )

    return indice


def carregar_resultados_manifesto(
    caminho_manifesto: Path,
    servico_esperado: str,
) -> list[dict[str, Any]]:
    """
    Lê os resultados bem-sucedidos de um manifesto
    de coleta.
    """
    manifesto = carregar_json_objeto(
        caminho_manifesto
    )

    source_service = manifesto.get(
        "source_service"
    )

    if source_service != servico_esperado:
        raise ValueError(
            f"Manifesto {caminho_manifesto} possui "
            f"source_service={source_service!r}; "
            f"esperado={servico_esperado!r}."
        )

    resultados = manifesto.get("results")

    if not isinstance(resultados, list):
        raise ValueError(
            f"O manifesto {caminho_manifesto} não "
            "contém uma lista em 'results'."
        )

    resultados_validos: list[
        dict[str, Any]
    ] = []

    for resultado in resultados:
        if not isinstance(resultado, dict):
            continue

        if resultado.get("status") != "success":
            continue

        raw_file = resultado.get("raw_file")

        if not isinstance(raw_file, str):
            raise ValueError(
                "Resultado de manifesto sem "
                "'raw_file' válido."
            )

        resultados_validos.append(resultado)

    return resultados_validos


def criar_daily_weather_id(
    location_slug: str,
    date_local: str,
    data_kind: str,
) -> str:
    """
    Gera um identificador determinístico.

    Previsão, histórico provisório e reanálise para a
    mesma data permanecem conceitualmente distintos porque
    data_kind participa da chave. No staging corrente,
    entretanto, existe apenas uma representação vigente
    para cada data/localidade.
    """
    conteudo = (
        f"open-meteo|"
        f"{location_slug}|"
        f"{date_local}|"
        f"{data_kind}"
    )

    hash_id = hashlib.sha256(
        conteudo.encode("utf-8")
    ).hexdigest()

    return (
        f"openmeteo-"
        f"{hash_id[:24]}"
    )


def converter_float(
    valor: Any,
) -> float | None:
    if valor is None:
        return None

    if isinstance(valor, bool):
        raise ValueError(
            "Valor booleano não pode ser convertido "
            "para float."
        )

    return float(valor)


def converter_int(
    valor: Any,
) -> int | None:
    if valor is None:
        return None

    if isinstance(valor, bool):
        raise ValueError(
            "Valor booleano não pode ser convertido "
            "para inteiro."
        )

    return int(valor)


def converter_texto(
    valor: Any,
) -> str | None:
    if valor is None:
        return None

    texto = str(valor).strip()

    return texto or None


def validar_bloco_daily(
    daily: dict[str, Any],
) -> list[str]:
    """
    Valida o alinhamento das séries diárias.

    Todos os campos presentes devem possuir o mesmo
    tamanho de daily.time.
    """
    datas = daily.get("time")

    if not isinstance(datas, list):
        raise ValueError(
            "O bloco daily não contém uma lista "
            "em 'time'."
        )

    if not datas:
        raise ValueError(
            "O bloco daily não contém datas."
        )

    quantidade = len(datas)

    for campo, valores in daily.items():
        if campo == "time":
            continue

        if not isinstance(valores, list):
            raise ValueError(
                f"O campo daily.{campo} não contém "
                "uma lista."
            )

        if len(valores) != quantidade:
            raise ValueError(
                f"O campo daily.{campo} possui "
                f"{len(valores)} posições, mas "
                f"daily.time possui {quantidade}."
            )

    return [
        str(data)
        for data in datas
    ]


def obter_valor_serie(
    daily: dict[str, Any],
    campo: str,
    indice: int,
) -> Any:
    """
    Retorna o valor de uma série diária.

    Campos ausentes são tratados como None porque
    histórico e previsão não possuem exatamente o
    mesmo conjunto de variáveis.
    """
    valores = daily.get(campo)

    if valores is None:
        return None

    if not isinstance(valores, list):
        raise ValueError(
            f"O campo daily.{campo} deveria ser "
            "uma lista."
        )

    if indice >= len(valores):
        raise ValueError(
            f"Índice {indice} fora da série "
            f"daily.{campo}."
        )

    return valores[indice]


def determinar_data_kind(
    source_service: str,
    date_local: str,
    raw_record: dict[str, Any],
) -> str:
    """
    Determina a natureza temporal de um registro diário.

    Forecast:
    - permanece forecast.

    Historical Weather:
    - D-5 até D-1 são historical_provisional;
    - D-15 até D-6 são historical_reanalysis.

    A fronteira é calculada a partir do end_date da
    própria requisição histórica armazenada no RAW.
    Isso torna a classificação determinística e não
    dependente da hora em que o parser for executado.
    """
    if source_service == "forecast":
        return "forecast"

    if source_service != "historical":
        raise ValueError(
            "Serviço Open-Meteo não reconhecido: "
            f"{source_service}"
        )

    parametros = raw_record.get(
        "request_parameters"
    )

    if not isinstance(
        parametros,
        dict,
    ):
        raise ValueError(
            "RAW histórico sem request_parameters."
        )

    data_final_texto = converter_texto(
        parametros.get("end_date")
    )

    if data_final_texto is None:
        raise ValueError(
            "RAW histórico sem end_date na requisição."
        )

    data_registro = date.fromisoformat(
        date_local
    )

    data_final = date.fromisoformat(
        data_final_texto
    )

    distancia_para_fim = (
        data_final
        - data_registro
    ).days

    if distancia_para_fim < 0:
        raise ValueError(
            "Registro histórico possui data posterior "
            "ao end_date da própria requisição: "
            f"{date_local} > {data_final_texto}."
        )

    if (
        distancia_para_fim
        < HISTORICAL_PROVISIONAL_DAYS
    ):
        return "historical_provisional"

    return "historical_reanalysis"


def parsear_raw_diario(
    raw_record: dict[str, Any],
    raw_path: Path,
    localidade: dict[str, Any],
) -> list[DailyWeatherRecord]:
    """
    Converte um RawExternalRecord de previsão ou
    histórico em registros diários normalizados.
    """
    source = converter_texto(
        raw_record.get("source")
    )

    source_service = converter_texto(
        raw_record.get("source_service")
    )

    raw_record_id = converter_texto(
        raw_record.get("raw_record_id")
    )

    raw_payload_hash = converter_texto(
        raw_record.get("payload_hash")
    )

    retrieved_at_utc = converter_texto(
        raw_record.get("retrieved_at_utc")
    )

    location_slug = converter_texto(
        raw_record.get("location_slug")
    )

    if source != "open-meteo":
        raise ValueError(
            f"Fonte inesperada no RAW: {source}"
        )

    if source_service is None:
        raise ValueError(
            "RAW sem source_service."
        )

    if raw_record_id is None:
        raise ValueError(
            "RAW sem raw_record_id."
        )

    if raw_payload_hash is None:
        raise ValueError(
            "RAW sem payload_hash."
        )

    if retrieved_at_utc is None:
        raise ValueError(
            "RAW sem retrieved_at_utc."
        )

    if location_slug is None:
        raise ValueError(
            "RAW sem location_slug."
        )

    slug_localidade = converter_texto(
        localidade.get("slug")
    )

    if slug_localidade != location_slug:
        raise ValueError(
            "A localidade do RAW não corresponde "
            "à localidade resolvida: "
            f"{location_slug} != {slug_localidade}"
        )

    payload = raw_record.get("payload")

    if not isinstance(payload, dict):
        raise ValueError(
            "RAW não contém objeto em 'payload'."
        )

    daily = payload.get("daily")

    if not isinstance(daily, dict):
        raise ValueError(
            "Payload não contém objeto em 'daily'."
        )

    daily_units = payload.get("daily_units")

    if daily_units is None:
        daily_units = {}

    if not isinstance(daily_units, dict):
        raise ValueError(
            "payload.daily_units deveria ser "
            "um objeto."
        )

    datas = validar_bloco_daily(daily)

    location_name = converter_texto(
        localidade.get("resolved_name")
    )

    country_code = converter_texto(
        localidade.get("country_code")
    )

    state_code = converter_texto(
        localidade.get(
            "requested_state_code"
        )
    )

    timezone_name = converter_texto(
        payload.get("timezone")
        or localidade.get("timezone")
    )

    if location_name is None:
        raise ValueError(
            f"Localidade {location_slug} sem nome."
        )

    if country_code is None:
        raise ValueError(
            f"Localidade {location_slug} sem país."
        )

    if timezone_name is None:
        raise ValueError(
            f"Localidade {location_slug} sem timezone."
        )

    latitude = converter_float(
        localidade.get("latitude")
    )

    longitude = converter_float(
        localidade.get("longitude")
    )

    if latitude is None or longitude is None:
        raise ValueError(
            f"Localidade {location_slug} sem "
            "coordenadas válidas."
        )

    registros: list[
        DailyWeatherRecord
    ] = []

    for indice, date_local in enumerate(datas):
        data_kind = determinar_data_kind(
            source_service=source_service,
            date_local=date_local,
            raw_record=raw_record,
        )

        registro = DailyWeatherRecord(
            daily_weather_id=(
                criar_daily_weather_id(
                    location_slug=location_slug,
                    date_local=date_local,
                    data_kind=data_kind,
                )
            ),
            source="open-meteo",
            source_service=source_service,
            data_kind=data_kind,
            location_slug=location_slug,
            location_name=location_name,
            state_code=state_code,
            country_code=country_code,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone_name,
            date_local=date_local,
            weather_code=converter_int(
                obter_valor_serie(
                    daily,
                    "weather_code",
                    indice,
                )
            ),
            temperature_2m_max=converter_float(
                obter_valor_serie(
                    daily,
                    "temperature_2m_max",
                    indice,
                )
            ),
            temperature_2m_mean=converter_float(
                obter_valor_serie(
                    daily,
                    "temperature_2m_mean",
                    indice,
                )
            ),
            temperature_2m_min=converter_float(
                obter_valor_serie(
                    daily,
                    "temperature_2m_min",
                    indice,
                )
            ),
            apparent_temperature_max=converter_float(
                obter_valor_serie(
                    daily,
                    "apparent_temperature_max",
                    indice,
                )
            ),
            apparent_temperature_mean=converter_float(
                obter_valor_serie(
                    daily,
                    "apparent_temperature_mean",
                    indice,
                )
            ),
            apparent_temperature_min=converter_float(
                obter_valor_serie(
                    daily,
                    "apparent_temperature_min",
                    indice,
                )
            ),
            precipitation_sum=converter_float(
                obter_valor_serie(
                    daily,
                    "precipitation_sum",
                    indice,
                )
            ),
            rain_sum=converter_float(
                obter_valor_serie(
                    daily,
                    "rain_sum",
                    indice,
                )
            ),
            showers_sum=converter_float(
                obter_valor_serie(
                    daily,
                    "showers_sum",
                    indice,
                )
            ),
            snowfall_sum=converter_float(
                obter_valor_serie(
                    daily,
                    "snowfall_sum",
                    indice,
                )
            ),
            precipitation_hours=converter_float(
                obter_valor_serie(
                    daily,
                    "precipitation_hours",
                    indice,
                )
            ),
            precipitation_probability_max=(
                converter_float(
                    obter_valor_serie(
                        daily,
                        "precipitation_probability_max",
                        indice,
                    )
                )
            ),
            sunrise=converter_texto(
                obter_valor_serie(
                    daily,
                    "sunrise",
                    indice,
                )
            ),
            sunset=converter_texto(
                obter_valor_serie(
                    daily,
                    "sunset",
                    indice,
                )
            ),
            daylight_duration=converter_float(
                obter_valor_serie(
                    daily,
                    "daylight_duration",
                    indice,
                )
            ),
            sunshine_duration=converter_float(
                obter_valor_serie(
                    daily,
                    "sunshine_duration",
                    indice,
                )
            ),
            wind_speed_10m_max=converter_float(
                obter_valor_serie(
                    daily,
                    "wind_speed_10m_max",
                    indice,
                )
            ),
            wind_gusts_10m_max=converter_float(
                obter_valor_serie(
                    daily,
                    "wind_gusts_10m_max",
                    indice,
                )
            ),
            wind_direction_10m_dominant=(
                converter_float(
                    obter_valor_serie(
                        daily,
                        "wind_direction_10m_dominant",
                        indice,
                    )
                )
            ),
            source_grid_latitude=converter_float(
                payload.get("latitude")
            ),
            source_grid_longitude=converter_float(
                payload.get("longitude")
            ),
            source_elevation=converter_float(
                payload.get("elevation")
            ),
            utc_offset_seconds=converter_int(
                payload.get("utc_offset_seconds")
            ),
            units=dict(daily_units),
            raw_record_id=raw_record_id,
            raw_payload_hash=raw_payload_hash,
            raw_file=str(
                raw_path.relative_to(BASE_DIR)
                if raw_path.is_relative_to(BASE_DIR)
                else raw_path
            ),
            retrieved_at_utc=retrieved_at_utc,
            parser_version=DAILY_PARSER_VERSION,
        )

        registros.append(registro)

    return registros


def parsear_manifesto(
    caminho_manifesto: Path,
    servico_esperado: str,
    localidades: dict[
        str,
        dict[str, Any],
    ],
) -> list[DailyWeatherRecord]:
    """
    Processa todos os RAWs referenciados por um
    manifesto.
    """
    resultados = carregar_resultados_manifesto(
        caminho_manifesto=caminho_manifesto,
        servico_esperado=servico_esperado,
    )

    registros: list[
        DailyWeatherRecord
    ] = []

    for resultado in resultados:
        location_slug = converter_texto(
            resultado.get("location_slug")
        )

        raw_file = converter_texto(
            resultado.get("raw_file")
        )

        if location_slug is None:
            raise ValueError(
                "Resultado de manifesto sem "
                "location_slug."
            )

        if raw_file is None:
            raise ValueError(
                "Resultado de manifesto sem raw_file."
            )

        localidade = localidades.get(
            location_slug
        )

        if localidade is None:
            raise ValueError(
                "Localidade do manifesto não foi "
                "encontrada em locations_resolved.json: "
                f"{location_slug}"
            )

        raw_path = resolver_caminho_projeto(
            raw_file
        )

        raw_record = carregar_json_objeto(
            raw_path
        )

        registros_raw = parsear_raw_diario(
            raw_record=raw_record,
            raw_path=raw_path,
            localidade=localidade,
        )

        logging.info(
            "%s registros diários extraídos de %s.",
            len(registros_raw),
            raw_path.name,
        )

        registros.extend(registros_raw)

    return registros


def remover_registros_duplicados(
    registros: list[DailyWeatherRecord],
) -> list[DailyWeatherRecord]:
    """
    Remove duplicidades pelo identificador diário.

    Em caso de repetição, o registro com coleta mais
    recente tem prioridade.
    """
    registros_por_id: dict[
        str,
        DailyWeatherRecord,
    ] = {}

    for registro in registros:
        existente = registros_por_id.get(
            registro.daily_weather_id
        )

        if existente is None:
            registros_por_id[
                registro.daily_weather_id
            ] = registro
            continue

        if (
            registro.retrieved_at_utc
            > existente.retrieved_at_utc
        ):
            registros_por_id[
                registro.daily_weather_id
            ] = registro

    return list(
        registros_por_id.values()
    )


def salvar_por_localidade(
    registros: list[DailyWeatherRecord],
) -> list[str]:
    """
    Salva um arquivo de staging por localidade.
    """
    grupos: dict[
        str,
        list[DailyWeatherRecord],
    ] = {}

    for registro in registros:
        grupos.setdefault(
            registro.location_slug,
            [],
        ).append(registro)

    arquivos_gerados: list[str] = []

    for location_slug, grupo in grupos.items():
        grupo.sort(
            key=lambda item: (
                item.date_local,
                item.data_kind,
            )
        )

        caminho = (
            STAGING_DAILY_DIR
            / (
                f"{location_slug}"
                f"__openmeteo_daily_30d.json"
            )
        )

        payload = {
            "schema_version": "1.0",
            "parser_version": DAILY_PARSER_VERSION,
            "generated_at_utc": agora_utc_iso(),
            "location_slug": location_slug,
            "record_count": len(grupo),
            "period_start": grupo[0].date_local,
            "period_end": grupo[-1].date_local,
            "records": [
                registro.to_dict()
                for registro in grupo
            ],
        }

        salvar_json(
            caminho,
            payload,
        )

        arquivos_gerados.append(
            str(caminho.relative_to(BASE_DIR))
        )

    return arquivos_gerados


def validar_quantidade_por_localidade(
    registros: list[DailyWeatherRecord],
) -> dict[str, int]:
    """
    Valida o marco de 30 dias por localidade.
    """
    contagens: dict[str, int] = {}

    for registro in registros:
        contagens[registro.location_slug] = (
            contagens.get(
                registro.location_slug,
                0,
            )
            + 1
        )

    for location_slug, quantidade in sorted(
        contagens.items()
    ):
        if (
            quantidade
            != EXPECTED_DAILY_RECORDS_PER_LOCATION
        ):
            logging.warning(
                (
                    "%s possui %s registros diários; "
                    "eram esperados %s."
                ),
                location_slug,
                quantidade,
                EXPECTED_DAILY_RECORDS_PER_LOCATION,
            )

    return contagens


def parsear_dados_diarios(
) -> dict[str, Any]:
    """
    Converte histórico e previsão para o staging
    diário compartilhado.

    A janela operacional permanece com 30 dias:
    - D-15 a D-6: historical_reanalysis;
    - D-5 a D-1: historical_provisional;
    - D0 a D+14: forecast.
    """
    localidades = carregar_indice_localidades()

    registros_historicos = parsear_manifesto(
        caminho_manifesto=(
            HISTORICAL_MANIFEST_PATH
        ),
        servico_esperado="historical",
        localidades=localidades,
    )

    registros_previsao = parsear_manifesto(
        caminho_manifesto=(
            FORECAST_MANIFEST_PATH
        ),
        servico_esperado="forecast",
        localidades=localidades,
    )

    registros = (
        registros_historicos
        + registros_previsao
    )

    registros = remover_registros_duplicados(
        registros
    )

    registros.sort(
        key=lambda item: (
            item.location_slug,
            item.date_local,
            item.data_kind,
        )
    )

    if not registros:
        raise ValueError(
            "Nenhum registro diário foi produzido."
        )

    contagens = validar_quantidade_por_localidade(
        registros
    )

    arquivos_por_localidade = (
        salvar_por_localidade(registros)
    )

    datas = [
        registro.date_local
        for registro in registros
    ]

    data_kinds = sorted(
        {
            registro.data_kind
            for registro in registros
        }
    )

    payload_consolidado = {
        "schema_version": "1.0",
        "parser_version": DAILY_PARSER_VERSION,
        "generated_at_utc": agora_utc_iso(),
        "record_count": len(registros),
        "location_count": len(contagens),
        "period_start": min(datas),
        "period_end": max(datas),
        "data_kinds": data_kinds,
        "records_per_location": contagens,
        "records": [
            registro.to_dict()
            for registro in registros
        ],
    }

    salvar_json(
        STAGING_DAILY_CONSOLIDATED_PATH,
        payload_consolidado,
    )

    manifesto = {
        "schema_version": "1.0",
        "parser_version": DAILY_PARSER_VERSION,
        "generated_at_utc": agora_utc_iso(),
        "historical_record_count": len(
            registros_historicos
        ),
        "historical_reanalysis_record_count": sum(
            1
            for registro in registros_historicos
            if registro.data_kind
            == "historical_reanalysis"
        ),
        "historical_provisional_record_count": sum(
            1
            for registro in registros_historicos
            if registro.data_kind
            == "historical_provisional"
        ),
        "historical_reanalysis_days_per_location": (
            HISTORICAL_REANALYSIS_DAYS
        ),
        "historical_provisional_days_per_location": (
            HISTORICAL_PROVISIONAL_DAYS
        ),
        "forecast_record_count": len(
            registros_previsao
        ),
        "consolidated_record_count": len(
            registros
        ),
        "location_count": len(contagens),
        "expected_records_per_location": (
            EXPECTED_DAILY_RECORDS_PER_LOCATION
        ),
        "records_per_location": contagens,
        "consolidated_file": str(
            STAGING_DAILY_CONSOLIDATED_PATH.relative_to(
                BASE_DIR
            )
        ),
        "location_files": (
            arquivos_por_localidade
        ),
    }

    salvar_json(
        STAGING_DAILY_MANIFEST_PATH,
        manifesto,
    )

    logging.info(
        "Staging diário consolidado salvo em: %s.",
        STAGING_DAILY_CONSOLIDATED_PATH,
    )

    return manifesto