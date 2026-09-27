import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from rest_framework.test import APIClient

from motor_sin.common.io import write_table
from motor_sin.signals.real_signal import build_real_system_signal
from motor_sin.sources.ons_dessem import SOURCE as DESSEM_SOURCE
from motor_tarifa.base_tariff.parser import prepare_tariffs
from web.studio.api import _hourly_payload
from web.studio.services import product
from web.studio.services.validation import _contextual_comparisons


class RegionalValidationSummaryTests(TestCase):
    def test_selects_contextual_forecast_for_each_region(self):
        runs = [
            {'slug': 'n-e2-ridge', 'region': 'N', 'comparison_group': 'auto_2023_2026', 'experiment': 'E2', 'algorithm': 'ridge', 'WAPE': .016},
            {'slug': 'n-e3-ridge', 'region': 'N', 'comparison_group': 'auto_2023_2026', 'experiment': 'E3', 'algorithm': 'ridge', 'WAPE': .021},
            {'slug': 'n-e3-xgb', 'region': 'N', 'comparison_group': 'auto_2023_2026', 'experiment': 'E3', 'algorithm': 'xgboost', 'WAPE': .020},
            {'slug': 'n-e1-ridge', 'region': 'N', 'comparison_group': 'other', 'experiment': 'E1', 'algorithm': 'ridge', 'WAPE': .024},
            {'slug': 's-e3-xgb', 'region': 'S', 'comparison_group': 'auto_2023_2026', 'experiment': 'E3', 'algorithm': 'xgboost', 'WAPE': .030},
            {'slug': 's-e2-ridge', 'region': 'S', 'comparison_group': 'auto_2023_2026', 'experiment': 'E2', 'algorithm': 'ridge', 'WAPE': .040},
            {'slug': 's-e1-xgb', 'region': 'S', 'comparison_group': 'auto_2023_2026', 'experiment': 'E1', 'algorithm': 'xgboost', 'WAPE': .025},
        ]

        with patch('web.studio.services.validation._dessem_benchmark', return_value=None):
            comparisons = {item['region']: item for item in _contextual_comparisons(runs)}

        self.assertEqual(comparisons['N']['forecast']['slug'], 'n-e3-xgb')
        self.assertEqual(comparisons['S']['forecast']['slug'], 's-e3-xgb')


class PredictaApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_swagger_ui_and_schema_are_exposed(self):
        docs = self.client.get('/api/docs/')
        schema = self.client.get('/api/schema/')

        self.assertEqual(docs.status_code, 200)
        self.assertEqual(schema.status_code, 200)
        self.assertIn('/api/v1/simulations/', schema.content.decode())

    def test_simulation_rejects_invalid_payload_without_running_pipeline(self):
        response = self.client.post(
            '/api/v1/simulations/',
            data={
                'cnpj': '12345678000199',
                'region': 'SE/CO',
                'distributor': 'DUMMY',
                'profile': 'DUMMY',
                'monthly_kwh': 0,
                'customer_type': 'residential',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('monthly_kwh', response.json())

    def test_profiles_reject_invalid_effective_date(self):
        response = self.client.get(
            '/api/v1/catalog/profiles/',
            {'cnpj': '12345678000199', 'effective_date': '20-09-2026'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'effective_date deve estar em YYYY-MM-DD.')

    def test_simulation_rejects_invalid_portfolio_assumptions(self):
        payload = {
            'cnpj': '12345678000199', 'region': 'SE/CO', 'distributor': 'DUMMY',
            'profile': 'DUMMY', 'monthly_kwh': 300,
        }
        for field, value in [('portfolio_customers', 0), ('portfolio_customers', 1.5),
                             ('participation_pct', -1), ('participation_pct', 101),
                             ('optimization_objective', 'unknown')]:
            with self.subTest(field=field, value=value):
                response = self.client.post('/api/v1/simulations/', data={**payload, field: value}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())


class DessemProductFlowTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = patch.object(product, '_dataset', side_effect=lambda relative, local: self.root / relative)
        self.paths.start()
        self.addCleanup(self.paths.stop)
        timestamps = pd.date_range('2026-06-01T03:00:00Z', periods=24, freq='h')
        self.forecast = pd.DataFrame({
            'interval_start_utc': timestamps, 'subsystem_id': 'SE/CO',
            'issue_time_utc': pd.Timestamp('2026-06-01T02:00:00Z'),
            'demand_p10_mw': 90., 'demand_p50_mw': 100., 'demand_p90_mw': 110.,
            'experiment': 'E3',
        })
        self.load = pd.DataFrame({
            'interval_start_utc': pd.date_range('2026-05-01T03:00:00Z', periods=24 * 30, freq='h'),
            'subsystem_id': 'SE/CO', 'load_mw': 100.,
        })
        self.schedule = pd.DataFrame({
            'interval_start_utc': timestamps, 'subsystem_id': 'SE/CO',
            'programmed_load_mw': 100., 'source': DESSEM_SOURCE,
            'available_at_utc': pd.Timestamp('2026-09-26T12:00:00Z'),
            'source_url': 'https://example.test/dessem.parquet', 'snapshot_sha256': 'a' * 64,
        })
        write_table(self.forecast, self.root / 'outputs/metrics/e3_real_pilot_predictions.parquet')
        write_table(self.load, self.root / 'data/processed/demand/load_hourly.parquet')
        write_table(self.schedule, self.root / 'data/processed/generation/dessem_schedule_hourly.parquet')

        self.tariffs, _ = prepare_tariffs(pd.DataFrame([{
            'SigAgente': 'TESTE', 'VlrTE': '300', 'VlrTUSD': '400',
            'DscUnidadeTerciaria': 'R$/MWh', 'DscSubGrupo': 'B1',
            'NomPostoTarifario': 'Não se aplica',
            'DatInicioVigencia': '01/01/2026', 'DatFimVigencia': '31/12/2026',
        }]))
        self.tariffs['distributor_cnpj'] = '12345678000199'
        write_table(self.tariffs, self.root / 'data/processed/tariff/base_tariffs.parquet')

    def test_replay_reconstructs_signal_with_required_dessem(self):
        signal, window = product.resolve_signal('SE/CO', mode='replay')
        self.assertEqual(window['source'], 'CONTEXTUAL_CLIMATE_BACKTEST')
        self.assertEqual(len(signal), 24)
        self.assertTrue(signal.supply_pressure.eq(.5).all())
        self.assertTrue(all('DESSEM_REPLAY_NOT_ASOF' in json.loads(flags) for flags in signal.quality_flags))

    def test_replay_uses_regional_contextual_predictions(self):
        regional = self.forecast.assign(subsystem_id='S')
        regional_path = self.root / 'outputs/metrics/model_validation/auto_e3_xgboost_s_2023_2026_predictions.parquet'
        write_table(regional, regional_path)
        write_table(pd.DataFrame([{
            'experiment': 'E3', 'segment': 'ALL', 'horizon': 'ALL', 'WAPE': .03,
        }]), regional_path.with_name('auto_e3_xgboost_s_2023_2026_metrics.csv'))
        write_table(self.schedule.assign(subsystem_id='S'), self.root / 'data/processed/generation/dessem_schedule_hourly.parquet')

        windows = product.replay_windows('S')

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]['source'], 'CONTEXTUAL_CLIMATE_BACKTEST')

    def test_incomplete_dessem_is_not_offered_as_a_replay(self):
        write_table(self.schedule.iloc[1:], self.root / 'data/processed/generation/dessem_schedule_hourly.parquet')
        self.assertEqual(product.replay_windows('SE/CO'), [])
        with self.assertRaisesRegex(ValueError, 'DESSEM completos'):
            product.resolve_signal('SE/CO', mode='replay')

    def test_published_contract_replay_is_also_enriched(self):
        (self.root / 'outputs/metrics/e3_real_pilot_predictions.parquet').unlink()
        signal = build_real_system_signal(forecast=self.forecast, load_history=self.load, climate_context=None, run_id='web-test')
        write_table(signal, self.root / 'outputs/contracts/system_signal_v1.parquet')
        enriched, window = product.resolve_signal('SE/CO', mode='replay')
        self.assertEqual(window['source'], 'SYSTEM_SIGNAL_V1')
        self.assertTrue(enriched.supply_pressure.eq(.5).all())
        self.assertEqual(json.loads(enriched.main_drivers_json.iloc[0])['dessem']['programmed_load_mw'], 100.)

    def test_retrospective_dessem_cannot_be_promoted_to_operational(self):
        signal, _ = product.resolve_signal('SE/CO', mode='replay')
        with patch.object(product, '_load_current_signal', return_value=signal):
            status = product.operational_status('SE/CO')
        self.assertFalse(status['available'])
        self.assertIn('DESSEM', status['reason'])

    def test_customer_tariff_and_api_use_the_dessem_reference(self):
        self.schedule['programmed_load_mw'] = range(80, 104)
        write_table(self.schedule, self.root / 'data/processed/generation/dessem_schedule_hourly.parquet')
        tariffs = self.tariffs
        with patch.object(product, 'distributor_info', return_value={}):
            result, hourly = product.simulate_customer(
                region='SE/CO', cnpj='12345678000199', distributor='TESTE',
                profile=tariffs.tariff_profile_id.iloc[0], monthly_kwh=300,
                customer_type='residential', mode='replay',
            )
        self.assertTrue(result['dessem']['retrospective'])
        self.assertEqual(result['dessem']['hours'], 24)
        expected = 100 / (100 + self.schedule['programmed_load_mw'])
        self.assertTrue((hourly['supply_pressure'].to_numpy(float) == expected.to_numpy()).all())
        expected_raw = 1 + .2 * (.6 * (2 * hourly['demand_pressure'] - 1) + .4 * (2 * hourly['supply_pressure'] - 1))
        self.assertTrue((hourly['raw_multiplier'] - expected_raw).abs().lt(1e-12).all())
        self.assertGreater(hourly['dynamic_tariff_rs_kwh'].nunique(), 1)
        payload = _hourly_payload(hourly)
        self.assertEqual(len(payload), 24)
        self.assertEqual(payload[0]['dessem_programmed_load_mw'], 80)
        self.assertAlmostEqual(payload[0]['supply_pressure'], 100 / 180)
        with patch.object(product, 'distributor_info', return_value={}):
            response = APIClient().post('/api/v1/simulations/', data={
                'region': 'SE/CO', 'cnpj': '12345678000199', 'distributor': 'TESTE',
                'profile': tariffs.tariff_profile_id.iloc[0], 'monthly_kwh': 300,
                'customer_type': 'residential', 'mode': 'replay',
            }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['dessem']['source'], DESSEM_SOURCE)
        self.assertTrue(body['dessem']['retrospective'])
        self.assertEqual(len(body['hourly']), 24)
        self.assertEqual(body['hourly'][0]['dessem_programmed_load_mw'], 80)
        self.assertAlmostEqual(body['hourly'][0]['supply_pressure'], 100 / 180)

    def test_portfolio_curve_accounts_for_participation_and_conserves_energy(self):
        reference_tariffs = None
        for participation in (0, 50, 100):
            with self.subTest(participation=participation), patch.object(product, 'distributor_info', return_value={}):
                response = APIClient().post('/api/v1/simulations/', data={
                    'region': 'SE/CO', 'cnpj': '12345678000199', 'distributor': 'TESTE',
                    'profile': self.tariffs.tariff_profile_id.iloc[0], 'monthly_kwh': 300,
                    'optimization_objective': 'flatten', 'portfolio_customers': 10,
                    'participation_pct': participation,
                }, format='json')
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                portfolio = body['portfolio']
                self.assertEqual(portfolio['participating_customers'], participation // 10)
                self.assertTrue(portfolio['is_illustrative'])
                self.assertEqual(portfolio['scope'], 'SIMULATED_PORTFOLIO_NOT_TOTAL_DISTRIBUTOR_LOAD')
                self.assertEqual(portfolio['savings_scope'], 'PARTICIPATING_CONSUMERS_NOT_DISTRIBUTOR_PROFIT')
                self.assertAlmostEqual(portfolio['customer_savings_24h_rs'], body['consumer']['savings_24h_rs'] * portfolio['participating_customers'])
                self.assertAlmostEqual(portfolio['customer_savings_month_rs'], portfolio['customer_savings_24h_rs'] * body['projection']['days'])
                self.assertTrue(portfolio['load_shape']['energy_preserved'])
                self.assertEqual(portfolio['load_shape']['is_flatter'], participation > 0)
                self.assertLessEqual(portfolio['peak_after_mw'], portfolio['peak_before_mw'] + 1e-9)
                self.assertLessEqual(body['optimization']['optimized_dynamic_cost_24h_rs'], body['optimization']['original_dynamic_cost_24h_rs'] + 1e-9)
                for hour in body['hourly']:
                    expected = (hour['consumption_kwh'] * (10 - participation / 10)
                                + hour['optimized_consumption_kwh'] * participation / 10) / 1000
                    self.assertAlmostEqual(hour['portfolio_before_mw'], hour['consumption_kwh'] / 100)
                    self.assertAlmostEqual(hour['portfolio_after_mw'], expected)
                tariffs = [hour['dynamic_rs_kwh'] for hour in body['hourly']]
                if reference_tariffs is not None:
                    self.assertEqual(tariffs, reference_tariffs)
                reference_tariffs = tariffs

    def test_savings_follow_the_selected_curve_and_daily_projection(self):
        self.schedule['programmed_load_mw'] = range(80, 104)
        write_table(self.schedule, self.root / 'data/processed/generation/dessem_schedule_hourly.parquet')
        for objective in ('flatten', 'cost'):
            with self.subTest(objective=objective), patch.object(product, 'distributor_info', return_value={}):
                result, hourly = product.simulate_customer(
                    region='SE/CO', cnpj='12345678000199', distributor='TESTE',
                    profile=self.tariffs.tariff_profile_id.iloc[0], monthly_kwh=300,
                    customer_type='residential', optimization_objective=objective,
                )
            consumer = result['consumer']
            expected = float(((hourly.consumption_kwh - hourly.optimized_consumption_kwh)
                              * hourly.dynamic_tariff_rs_kwh).sum())
            self.assertEqual(consumer['objective'], objective)
            self.assertTrue(hourly.consumer_optimized_consumption_kwh.equals(hourly.optimized_consumption_kwh))
            self.assertAlmostEqual(consumer['savings_24h_rs'], expected)
            self.assertAlmostEqual(consumer['savings_24h_rs'], result['optimization']['potential_savings_24h_rs'])
            self.assertAlmostEqual(consumer['savings_month_rs'], expected * result['projection']['days'])
            self.assertFalse(result['projection']['is_forecast'])
            self.assertEqual(result['projection']['method'], 'REPEAT_SELECTED_24H_AVERAGE_MONTH')

    def test_product_renders_customer_and_portfolio_load_curves(self):
        with (
            patch.object(product, 'distributor_info', return_value={}),
            patch('web.studio.views.distributor_catalog', return_value=pd.DataFrame()),
            patch('web.studio.views.distributor_info', return_value={}),
            patch('web.studio.views.profiles_for_location', return_value=[]),
            patch('web.studio.views.available_regions', return_value={'SE/CO': True}),
        ):
            response = self.client.post('/produto/', data={
                'region': 'SE/CO', 'cnpj': '12345678000199', 'distributor': 'TESTE',
                'profile': self.tariffs.tariff_profile_id.iloc[0], 'monthly_kwh': 300,
                'portfolio_customers': 10, 'participation_pct': 50,
            })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['error'])
        self.assertContains(response, 'id="consumer-cost-chart"', count=1)
        self.assertContains(response, 'id="portfolio-chart"', count=1)
        self.assertContains(response, 'id="consumer-daily-savings"', count=1)
        self.assertContains(response, 'id="consumer-monthly-savings"', count=1)
        self.assertContains(response, 'id="portfolio-daily-savings"', count=1)
        self.assertContains(response, 'Não é uma previsão mensal')
        self.assertContains(response, 'Fator de carga')
        self.assertContains(response, 'Não é a carga total ou medida da distribuidora')
        result = response.context['result']
        self.assertEqual(result['optimization']['objective'], 'flatten')
        self.assertEqual(result['portfolio']['participating_customers'], 5)
        self.assertEqual(len(response.context['hourly']), 24)
        self.assertIn('portfolio_after_mw', response.context['hourly'][0])

    def test_pipeline_dessem_replay_requires_explicit_option(self):
        from web.studio.services.stage_registry import build_command

        self.assertNotIn('--allow-dessem-replay', build_command('build_signal', {}))
        command = build_command('build_signal', {'allow_dessem_replay': '1'})
        self.assertIn('--allow-dessem-replay', command)

    def test_historical_bridge_forwards_explicit_dessem_replay(self):
        from runpy import run_path

        with patch('sys.argv', ['42_run_historical_mvp_bridge.py', '--allow-dessem-replay']), patch('subprocess.run') as run:
            run_path(str(product.ROOT / 'scripts/42_run_historical_mvp_bridge.py'), run_name='__main__')
        self.assertIn('--allow-dessem-replay', run.call_args.args[0])
