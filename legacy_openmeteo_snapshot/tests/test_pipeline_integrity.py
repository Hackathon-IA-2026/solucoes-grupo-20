from __future__ import annotations

import json
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from openmeteo_pipeline.config import (
    EVENT_RULES_CONFIG_PATH,
    EXPECTED_DAILY_RECORDS_PER_LOCATION,
    FORECAST_DAYS,
    HISTORICAL_DAYS,
    HISTORICAL_PROVISIONAL_DAYS,
    HISTORICAL_REANALYSIS_DAYS,
    LOCATIONS_CONFIG_PATH,
    STAGING_DAILY_CONSOLIDATED_PATH,
    STAGING_EVENTS_DIR,
    TEMPERATURE_BASELINE_CONSOLIDATED_PATH,
    WEATHER_DETECTOR_VERSION,
    WEATHER_EVENT_CANDIDATES_MANIFEST_PATH,
    WEATHER_EVENT_CANDIDATES_PATH,
)
from openmeteo_pipeline.detectors import (
    EVENT_TITLES,
    carregar_indice_baseline,
    carregar_regras_clima,
    detectar_eventos_climaticos,
)


# =============================================================================
# CONSTANTES DO TESTE
# =============================================================================

EXPECTED_EVENT_TYPES = {
    "unusually_hot_day",
    "extreme_heat_day",
    "heat_wave_candidate",
    "unusually_cold_day",
    "extreme_cold_day",
    "cold_wave_candidate",
    "heavy_rain_day",
    "extreme_rain_day",
    "strong_wind_day",
    "severe_wind_day",
    "extreme_wind_day",
    "storm_candidate",
}


DETECTABLE_DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_gusts_10m_max",
)


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def carregar_json(
    caminho: Path,
) -> dict[str, Any]:
    if not caminho.exists():
        raise AssertionError(
            f"Arquivo obrigatório não encontrado: {caminho}"
        )

    with caminho.open(
        "r",
        encoding="utf-8",
    ) as arquivo:
        payload = json.load(arquivo)

    if not isinstance(payload, dict):
        raise AssertionError(
            f"O arquivo não contém um objeto JSON: {caminho}"
        )

    return payload


def carregar_localidades_ativas() -> set[str]:
    payload = carregar_json(
        LOCATIONS_CONFIG_PATH
    )

    localidades = payload.get("locations")

    if not isinstance(localidades, list):
        raise AssertionError(
            "locations.json não contém uma lista "
            "válida em 'locations'."
        )

    resultado: set[str] = set()

    for localidade in localidades:
        if not isinstance(localidade, dict):
            continue

        if localidade.get("active") is not True:
            continue

        slug = localidade.get("slug")

        if not isinstance(slug, str):
            raise AssertionError(
                "Localidade ativa sem slug válido."
            )

        resultado.add(slug)

    return resultado


# =============================================================================
# TESTE DE INTEGRIDADE
# =============================================================================

class PipelineIntegrityTestCase(
    unittest.TestCase
):

    # -------------------------------------------------------------------------
    # CONFIGURAÇÃO
    # -------------------------------------------------------------------------

    def test_01_localidades_configuradas(
        self,
    ) -> None:
        localidades = (
            carregar_localidades_ativas()
            )

        localidades_esperadas = {
            "rio_branco_ac",
            "maceio_al",
            "macapa_ap",
            "manaus_am",
            "salvador_ba",
            "fortaleza_ce",
            "brasilia_df",
            "vitoria_es",
            "goiania_go",
            "sao_luis_ma",
            "cuiaba_mt",
            "campo_grande_ms",
            "belo_horizonte_mg",
            "belem_pa",
            "joao_pessoa_pb",
            "curitiba_pr",
            "recife_pe",
            "teresina_pi",
            "rio_de_janeiro_rj",
            "natal_rn",
            "porto_alegre_rs",
            "porto_velho_ro",
            "boa_vista_rr",
            "florianopolis_sc",
            "sao_paulo_sp",
            "aracaju_se",
            "palmas_to",
        }

        self.assertEqual(
            len(localidades),
            27,
        )

        self.assertEqual(
            localidades,
            localidades_esperadas,
        )

    # -------------------------------------------------------------------------
    # REGRAS
    # -------------------------------------------------------------------------

    def test_02_regras_climaticas_completas(
        self,
    ) -> None:
        regras = carregar_regras_clima()

        tipos_configurados: set[str] = set()

        for nome_secao in (
            "temperature_events",
            "precipitation_events",
            "wind_events",
            "storm_events",
        ):
            secao = regras[nome_secao]

            tipos_configurados.update(
                secao.keys()
            )

        self.assertEqual(
            tipos_configurados,
            EXPECTED_EVENT_TYPES,
        )

        self.assertEqual(
            set(EVENT_TITLES),
            EXPECTED_EVENT_TYPES,
        )

    def test_03_limites_operacionais(
        self,
    ) -> None:
        regras = carregar_regras_clima()

        vento = regras[
            "wind_events"
        ]

        self.assertEqual(
            float(
                vento[
                    "strong_wind_day"
                ][
                    "threshold"
                ]
            ),
            60.0,
        )

        self.assertEqual(
            float(
                vento[
                    "severe_wind_day"
                ][
                    "threshold"
                ]
            ),
            80.0,
        )

        self.assertEqual(
            float(
                vento[
                    "extreme_wind_day"
                ][
                    "threshold"
                ]
            ),
            100.0,
        )

        chuva = regras[
            "precipitation_events"
        ]

        self.assertEqual(
            float(
                chuva[
                    "heavy_rain_day"
                ][
                    "threshold"
                ]
            ),
            50.0,
        )

        self.assertEqual(
            float(
                chuva[
                    "extreme_rain_day"
                ][
                    "threshold"
                ]
            ),
            100.0,
        )

        tempestade = regras[
            "storm_events"
        ][
            "storm_candidate"
        ]

        self.assertEqual(
            set(
                tempestade[
                    "forecast_weather_codes"
                ]
            ),
            {
                95,
                96,
                99,
            },
        )

        self.assertEqual(
            float(
                tempestade[
                    "minimum_precipitation_mm"
                ]
            ),
            30.0,
        )

        self.assertEqual(
            float(
                tempestade[
                    "minimum_wind_gust_kmh"
                ]
            ),
            60.0,
        )

    # -------------------------------------------------------------------------
    # BASELINE
    # -------------------------------------------------------------------------

    def test_04_baseline_cobre_todas_localidades(
        self,
    ) -> None:
        localidades = (
            carregar_localidades_ativas()
        )

        baseline = (
            carregar_indice_baseline()
        )

        self.assertEqual(
            set(baseline),
            localidades,
        )

    def test_05_baseline_tem_12_meses(
        self,
    ) -> None:
        baseline = (
            carregar_indice_baseline()
        )

        for slug, localidade in baseline.items():
            with self.subTest(
                location_slug=slug
            ):
                meses = localidade.get(
                    "months"
                )

                self.assertIsInstance(
                    meses,
                    list,
                )

                self.assertEqual(
                    len(meses),
                    12,
                )

                meses_encontrados = {
                    int(item["month"])
                    for item in meses
                }

                self.assertEqual(
                    meses_encontrados,
                    set(
                        range(
                            1,
                            13,
                        )
                    ),
                )

    def test_06_percentis_baseline_sao_coerentes(
        self,
    ) -> None:
        baseline = (
            carregar_indice_baseline()
        )

        metricas = (
            "temperature_2m_max",
            "temperature_2m_min",
        )

        for slug, localidade in baseline.items():
            for mes in localidade["months"]:
                for metrica in metricas:
                    with self.subTest(
                        location_slug=slug,
                        month=mes["month"],
                        metric=metrica,
                    ):
                        limites = mes[
                            "thresholds"
                        ][
                            metrica
                        ]

                        media = limites.get(
                            "mean"
                        )

                        self.assertIsInstance(
                            media,
                            (int, float),
                        )

                        p05 = float(
                            limites["p05"]
                        )

                        p10 = float(
                            limites["p10"]
                        )

                        p90 = float(
                            limites["p90"]
                        )

                        p95 = float(
                            limites["p95"]
                        )

                        self.assertLessEqual(
                            p05,
                            p10,
                        )

                        self.assertLessEqual(
                            p10,
                            p90,
                        )

                        self.assertLessEqual(
                            p90,
                            p95,
                        )

    # -------------------------------------------------------------------------
    # STAGING DIÁRIO
    # -------------------------------------------------------------------------

    def test_07_staging_diario_cobre_localidades(
        self,
    ) -> None:
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload.get(
            "records"
        )

        self.assertIsInstance(
            registros,
            list,
        )

        localidades_esperadas = (
            carregar_localidades_ativas()
        )

        localidades_encontradas = {
            str(
                registro[
                    "location_slug"
                ]
            )
            for registro in registros
        }

        self.assertEqual(
            localidades_encontradas,
            localidades_esperadas,
        )

    def test_08_quantidade_diaria_por_localidade(
        self,
    ) -> None:
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        contagem = Counter(
            str(
                registro[
                    "location_slug"
                ]
            )
            for registro in registros
        )

        localidades = (
            carregar_localidades_ativas()
        )

        self.assertEqual(
            EXPECTED_DAILY_RECORDS_PER_LOCATION,
            (
                HISTORICAL_REANALYSIS_DAYS
                + HISTORICAL_PROVISIONAL_DAYS
                + FORECAST_DAYS
            ),
        )

        for slug in localidades:
            with self.subTest(
                location_slug=slug
            ):
                self.assertEqual(
                    contagem[slug],
                    EXPECTED_DAILY_RECORDS_PER_LOCATION,
                )

    def test_09_divisao_temporal_dos_dados(
        self,
    ) -> None:
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        localidades = (
            carregar_localidades_ativas()
        )

        for slug in localidades:
            registros_localidade = [
                registro
                for registro in registros
                if registro[
                    "location_slug"
                ] == slug
            ]

            contagem_tipos = Counter(
                str(
                    registro[
                        "data_kind"
                    ]
                )
                for registro
                in registros_localidade
            )

            with self.subTest(
                location_slug=slug
            ):
                self.assertEqual(
                    contagem_tipos[
                        "historical_reanalysis"
                    ],
                    HISTORICAL_REANALYSIS_DAYS,
                )

                self.assertEqual(
                    contagem_tipos[
                        "historical_provisional"
                    ],
                    HISTORICAL_PROVISIONAL_DAYS,
                )

                self.assertEqual(
                    contagem_tipos[
                        "forecast"
                    ],
                    FORECAST_DAYS,
                )

    def test_09b_ordem_das_faixas_temporais(
        self,
    ) -> None:
        """
        Garante que a representação corrente seja:

        D-15 ... D-6 -> historical_reanalysis
        D-5  ... D-1 -> historical_provisional
        D0   ... D+14 -> forecast
        """
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        localidades = (
            carregar_localidades_ativas()
        )

        esperado = (
            [
                "historical_reanalysis"
            ]
            * HISTORICAL_REANALYSIS_DAYS
            + [
                "historical_provisional"
            ]
            * HISTORICAL_PROVISIONAL_DAYS
            + [
                "forecast"
            ]
            * FORECAST_DAYS
        )

        for slug in localidades:
            registros_localidade = sorted(
                (
                    registro
                    for registro in registros
                    if registro[
                        "location_slug"
                    ] == slug
                ),
                key=lambda item: str(
                    item["date_local"]
                ),
            )

            tipos = [
                str(
                    registro[
                        "data_kind"
                    ]
                )
                for registro
                in registros_localidade
            ]

            with self.subTest(
                location_slug=slug
            ):
                self.assertEqual(
                    tipos,
                    esperado,
                )

    def test_10_sem_datas_duplicadas(
        self,
    ) -> None:
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        localidades = (
            carregar_localidades_ativas()
        )

        for slug in localidades:
            datas = [
                str(
                    registro[
                        "date_local"
                    ]
                )
                for registro in registros
                if registro[
                    "location_slug"
                ] == slug
            ]

            with self.subTest(
                location_slug=slug
            ):
                self.assertEqual(
                    len(datas),
                    len(
                        set(datas)
                    ),
                )

    def test_11_sem_lacunas_temporais(
        self,
    ) -> None:
        """
        Este é um teste crítico.

        Ter 30 registros não basta:
        precisamos de 30 dias consecutivos.
        """
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        localidades = (
            carregar_localidades_ativas()
        )

        erros: list[str] = []

        for slug in sorted(localidades):
            datas = sorted(
                date.fromisoformat(
                    str(
                        registro[
                            "date_local"
                        ]
                    )
                )
                for registro in registros
                if registro[
                    "location_slug"
                ] == slug
            )

            for anterior, atual in zip(
                datas,
                datas[1:],
            ):
                diferenca = (
                    atual - anterior
                ).days

                if diferenca != 1:
                    erros.append(
                        f"{slug}: "
                        f"{anterior.isoformat()} "
                        "-> "
                        f"{atual.isoformat()} "
                        f"({diferenca} dias)"
                    )

        self.assertEqual(
            erros,
            [],
            msg=(
                "Foram encontradas lacunas "
                "no staging diário:\n"
                + "\n".join(erros)
            ),
        )

    def test_12_registros_nao_sao_vazios(
        self,
    ) -> None:
        """
        Um registro de previsão não pode ocupar
        um dia da janela sem conter nenhuma das
        variáveis usadas pelos detectores.
        """
        payload = carregar_json(
            STAGING_DAILY_CONSOLIDATED_PATH
        )

        registros = payload[
            "records"
        ]

        vazios: list[str] = []

        for registro in registros:
            possui_dado = any(
                registro.get(campo)
                is not None
                for campo
                in DETECTABLE_DAILY_FIELDS
            )

            if possui_dado:
                continue

            vazios.append(
                (
                    f"{registro['location_slug']}"
                    ":"
                    f"{registro['date_local']}"
                )
            )

        self.assertEqual(
            vazios,
            [],
            msg=(
                "Registros sem dados "
                "meteorológicos detectáveis:\n"
                + "\n".join(vazios)
            ),
        )

    # -------------------------------------------------------------------------
    # DETECTOR END-TO-END
    # -------------------------------------------------------------------------

    def test_13_detector_executa_end_to_end(
        self,
    ) -> None:
        manifesto = (
            detectar_eventos_climaticos()
        )

        self.assertEqual(
            manifesto[
                "detector_version"
            ],
            WEATHER_DETECTOR_VERSION,
        )

        self.assertEqual(
            manifesto[
                "location_count"
            ],
            len(
                carregar_localidades_ativas()
            ),
        )

        self.assertTrue(
            WEATHER_EVENT_CANDIDATES_PATH.exists()
        )

        self.assertTrue(
            WEATHER_EVENT_CANDIDATES_MANIFEST_PATH.exists()
        )

    def test_14_candidatos_tem_contrato_valido(
        self,
    ) -> None:
        if not (
            WEATHER_EVENT_CANDIDATES_PATH.exists()
        ):
            detectar_eventos_climaticos()

        payload = carregar_json(
            WEATHER_EVENT_CANDIDATES_PATH
        )

        candidatos = payload.get(
            "candidates"
        )

        self.assertIsInstance(
            candidatos,
            list,
        )

        self.assertEqual(
            payload[
                "candidate_count"
            ],
            len(candidatos),
        )

        ids: set[str] = set()

        for candidato in candidatos:
            candidate_id = str(
                candidato[
                    "candidate_id"
                ]
            )

            self.assertTrue(
                candidate_id.startswith(
                    "weather-"
                )
            )

            self.assertNotIn(
                candidate_id,
                ids,
            )

            ids.add(
                candidate_id
            )

            self.assertEqual(
                candidato["source"],
                "open-meteo",
            )

            self.assertEqual(
                candidato[
                    "source_service"
                ],
                "weather_detector",
            )

            self.assertIn(
                candidato[
                    "event_type"
                ],
                EXPECTED_EVENT_TYPES,
            )

            self.assertIn(
                candidato[
                    "event_family"
                ],
                {
                    "heat",
                    "cold",
                    "precipitation",
                    "wind",
                    "storm",
                },
            )

            self.assertIn(
                candidato[
                    "severity"
                ],
                {
                    "moderate",
                    "severe",
                    "extreme",
                },
            )

            self.assertIn(
                candidato[
                    "status"
                ],
                {
                    "historical_reanalysis",
                    "provisional",
                    "forecast",
                    "mixed",
                },
            )

            self.assertEqual(
                candidato[
                    "detector_version"
                ],
                WEATHER_DETECTOR_VERSION,
            )

            self.assertTrue(
                candidato[
                    "source_record_ids"
                ]
            )

            self.assertTrue(
                candidato[
                    "source_payload_hashes"
                ]
            )

            self.assertTrue(
                candidato[
                    "daily_weather_ids"
                ]
            )

    def test_15_contagens_do_detector_batem(
        self,
    ) -> None:
        payload = carregar_json(
            WEATHER_EVENT_CANDIDATES_PATH
        )

        candidatos = payload[
            "candidates"
        ]

        por_tipo = Counter(
            candidato[
                "event_type"
            ]
            for candidato in candidatos
        )

        por_familia = Counter(
            candidato[
                "event_family"
            ]
            for candidato in candidatos
        )

        por_severidade = Counter(
            candidato[
                "severity"
            ]
            for candidato in candidatos
        )

        self.assertEqual(
            dict(
                sorted(
                    por_tipo.items()
                )
            ),
            payload[
                "candidate_count_by_type"
            ],
        )

        self.assertEqual(
            dict(
                sorted(
                    por_familia.items()
                )
            ),
            payload[
                "candidate_count_by_family"
            ],
        )

        self.assertEqual(
            dict(
                sorted(
                    por_severidade.items()
                )
            ),
            payload[
                "candidate_count_by_severity"
            ],
        )

    def test_16_um_arquivo_por_localidade(
        self,
    ) -> None:
        localidades = (
            carregar_localidades_ativas()
        )

        for slug in localidades:
            caminho = (
                STAGING_EVENTS_DIR
                / (
                    f"{slug}"
                    "__weather_event_candidates.json"
                )
            )

            with self.subTest(
                location_slug=slug
            ):
                self.assertTrue(
                    caminho.exists(),
                    msg=(
                        "Arquivo de candidatos "
                        "não encontrado: "
                        f"{caminho}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()