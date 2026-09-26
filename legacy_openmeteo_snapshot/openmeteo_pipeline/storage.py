from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def agora_utc_iso() -> str:
    """
    Retorna o instante atual em UTC no formato ISO 8601.
    """
    return datetime.now(
        timezone.utc
    ).isoformat()


def agora_utc_para_arquivo() -> str:
    """
    Retorna timestamp apropriado para nomes de arquivo.
    """
    return datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


def salvar_json(
    caminho: Path,
    conteudo: Any,
) -> None:
    """
    Salva um objeto Python em JSON UTF-8.
    """
    caminho.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with caminho.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            conteudo,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


def serializar_json_canonico(
    conteudo: Any,
) -> str:
    """
    Produz uma representação JSON determinística.

    Essa representação é usada apenas para calcular
    o hash do conteúdo.
    """
    return json.dumps(
        conteudo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def calcular_hash_sha256(
    conteudo: Any,
) -> str:
    """
    Calcula SHA-256 de um objeto serializável em JSON.
    """
    texto_canonico = serializar_json_canonico(
        conteudo
    )

    return hashlib.sha256(
        texto_canonico.encode("utf-8")
    ).hexdigest()

def preparar_payload_para_hash(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Remove metadados voláteis que não representam
    alteração dos dados meteorológicos.

    O payload original não é modificado e continua
    sendo salvo integralmente na camada RAW.
    """
    payload_para_hash = dict(payload)

    payload_para_hash.pop(
        "generationtime_ms",
        None,
    )

    return payload_para_hash


def localizar_registro_identico(
    diretorio: Path,
    location_slug: str,
    source_service: str,
    content_hash: str,
) -> Path | None:
    """
    Procura um arquivo RAW com o mesmo hash para a
    mesma localidade e serviço.
    """
    padrao = (
        f"{location_slug}"
        f"__{source_service}"
        f"__*"
        f"__{content_hash}.json"
    )

    arquivos = sorted(
        diretorio.glob(padrao)
    )

    if not arquivos:
        return None

    return arquivos[-1]


def persistir_raw_external_record(
    *,
    diretorio: Path,
    source: str,
    source_service: str,
    source_endpoint: str,
    location_slug: str,
    external_id: str,
    request_parameters: dict[str, Any],
    payload: dict[str, Any],
    http_status: int,
    retrieved_at_utc: str,
) -> tuple[Path, bool, str]:
    """
    Persiste uma resposta externa no formato da
    camada RAW.

    Retorno:
    1. caminho do arquivo;
    2. True quando um novo arquivo foi salvo;
    3. hash SHA-256 do conteúdo.
    """
    payload_para_hash = preparar_payload_para_hash(
        payload
    )

    conteudo_para_hash = {
        "request_parameters": request_parameters,
        "payload": payload_para_hash,
    }

    content_hash = calcular_hash_sha256(
            conteudo_para_hash
        )

    registro_existente = localizar_registro_identico(
        diretorio=diretorio,
        location_slug=location_slug,
        source_service=source_service,
        content_hash=content_hash,
    )

    if registro_existente is not None:
        return (
            registro_existente,
            False,
            content_hash,
        )

    timestamp_arquivo = agora_utc_para_arquivo()

    nome_arquivo = (
        f"{location_slug}"
        f"__{source_service}"
        f"__{timestamp_arquivo}"
        f"__{content_hash}.json"
    )

    caminho = diretorio / nome_arquivo

    raw_record_id = (
        f"{source_service}"
        f":{location_slug}"
        f":{content_hash[:16]}"
    )

    registro = {
        "schema_version": "1.0",
        "raw_record_id": raw_record_id,
        "source": source,
        "source_service": source_service,
        "source_endpoint": source_endpoint,
        "external_id": external_id,
        "location_slug": location_slug,
        "request_parameters": request_parameters,
        "payload_hash": content_hash,
        "source_published_at": None,
        "source_updated_at": None,
        "retrieved_at_utc": retrieved_at_utc,
        "http_status": http_status,
        "processing_status": "pending",
        "processing_error": None,
        "payload": payload,
    }

    salvar_json(
        caminho,
        registro,
    )

    return (
        caminho,
        True,
        content_hash,
    )

def persistir_raw_current_record(
    *,
    diretorio: Path,
    nome_arquivo: str,
    source: str,
    source_service: str,
    location_slug: str,
    request_url: str,
    request_parameters: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persiste somente o estado corrente de uma fonte.

    Diferentemente de persistir_raw_external_record(),
    esta função não mantém snapshots sucessivos.
    O mesmo arquivo é sobrescrito a cada atualização.

    Uso principal:
    - previsão meteorológica corrente.
    """
    diretorio.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload_para_hash = preparar_payload_para_hash(
        payload
    )

    conteudo_para_hash = {
        "request_parameters": request_parameters,
        "payload": payload_para_hash,
    }

    payload_hash = calcular_hash_sha256(
        conteudo_para_hash
    )

    retrieved_at_utc = agora_utc_iso()

    raw_record_id = (
        f"{source_service}:"
        f"{location_slug}:"
        f"{payload_hash[:16]}"
    )

    caminho = (
        diretorio
        / nome_arquivo
    )

    registro_raw = {
        "schema_version": "1.0",
        "raw_record_id": raw_record_id,
        "source": source,
        "source_service": source_service,
        "location_slug": location_slug,
        "request_url": request_url,
        "request_parameters": (
            request_parameters
        ),
        "retrieved_at_utc": (
            retrieved_at_utc
        ),
        "payload_hash": payload_hash,
        "payload": payload,
    }

    salvar_json(
        caminho,
        registro_raw,
    )

    return {
        "raw_record_id": raw_record_id,
        "payload_hash": payload_hash,
        "raw_file": caminho,
        "retrieved_at_utc": (
            retrieved_at_utc
        ),
        "created_new_raw": True,
    }