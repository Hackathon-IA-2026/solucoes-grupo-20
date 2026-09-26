from django.test import TestCase
from django.urls import reverse


class StudioWebSmokeTests(TestCase):
    def test_dataset_path_uses_s3_prefix_and_caches_download(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from django.test import override_settings
        from web.studio.services.datasets import dataset_path

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / 'data' / 'processed' / 'sample.parquet'
            client = patch('web.studio.services.datasets.boto3.client').start().return_value
            client.download_file.side_effect = lambda bucket, key, filename: Path(filename).write_bytes(b'dataset')
            try:
                with patch.dict(os.environ, {'S3_ATANORA': 's3://atanora-data/predicta'}):
                    with override_settings(PREDICTA_S3_CACHE_ROOT=Path(temp_dir)):
                        self.assertEqual(dataset_path('data/processed/sample.parquet', Path('/missing/sample.parquet')), target)
                        self.assertEqual(target.read_bytes(), b'dataset')
                        self.assertEqual(dataset_path('data/processed/sample.parquet', Path('/missing/sample.parquet')), target)
            finally:
                patch.stopall()

        client.download_file.assert_called_once_with('atanora-data', 'predicta/data/processed/sample.parquet', str(target))

    def test_dataset_path_keeps_local_source_without_s3_configuration(self):
        import os
        from pathlib import Path
        from unittest.mock import patch

        from web.studio.services.datasets import dataset_path

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('S3_ATANORA', None)
            local = Path('/tmp/local-dataset.parquet')
            self.assertEqual(dataset_path('data/processed/sample.parquet', local), local)

    def test_human_date_component_formats_iso_and_date_values(self):
        from django.template import Context, Template

        template = Template('{% load date_display %}{% human_date value %}')
        self.assertIn('02/01/2026 00:04', template.render(Context({'value': '2026-01-02T03:04:05.123Z'})))
        self.assertIn('31/12/2025', template.render(Context({'value': '2025-12-31'})))
        self.assertIn('>02/01/2026 00:04</time>', template.render(Context({'value': '2026-01-02T03:04:05.123Z'})))

    def test_main_pages_render_without_project_artifacts(self):
        for name in ['dashboard','automation','data','features','territory','modeling','validation','models','product','pipeline']:
            response=self.client.get(reverse(f'studio:{name}'))
            self.assertEqual(response.status_code,200,name)

    def test_tariff_profile_api_is_safe_without_processed_tariffs(self):
        response=self.client.get(reverse('studio:api_profiles'),{'cnpj':'00000000000000','region':'SE/CO'})
        self.assertEqual(response.status_code,200)
        self.assertIn('profiles',response.json())

    def test_distribution_geojson_api_uses_real_concession_file(self):
        response=self.client.get(reverse('studio:api_distribution_areas'))
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertEqual(payload.get('type'),'FeatureCollection')
        self.assertGreaterEqual(len(payload.get('features',[])),100)
        props=payload['features'][0]['properties']
        self.assertIn('cnpj_digits',props)
        self.assertIn('subsystem_id',props)

    def test_pipeline_registry_params_are_iterable(self):
        from web.studio.services.stage_registry import STAGES, Param
        for stage in STAGES:
            with self.subTest(stage=stage.id):
                self.assertIsInstance(stage.params, tuple)
                self.assertTrue(all(isinstance(p, Param) for p in stage.params))


    def test_product_template_renders_real_simulation_result_shape(self):
        """Regression test for the nested customer/concession result returned by Motor 2."""
        from django.template.loader import render_to_string

        result = {
            'customer': {
                'distributor_id': 'CEMIG-D',
                'subsystem_id': 'SE/CO',
            },
            'concession': {
                'sigla': 'CEMIG-D',
                'uf': 'MG',
            },
            'reference_tariff_mean_rs_kwh': 0.85858,
            'dynamic_tariff_mean_rs_kwh': 0.8652,
            'reference_cost_24h_rs': 8.46,
            'dynamic_cost_24h_rs': 8.46,
            'difference_rs': 0.0,
            'difference_pct': 0.0,
            'simulation_scope': 'test',
        }
        html = render_to_string('studio/product.html', {
            'page': 'product',
            'regions': [],
            'distributor_options': [],
            'profiles': [],
            'result': result,
            'hourly': [],
            'error': None,
            'selected_region': 'SE/CO',
            'selected_cnpj': '06981180000116',
            'selected_distributor': 'CEMIG-D',
            'selected_profile': '',
            'selected_info': result['concession'],
            'monthly_kwh': '300',
            'customer_type': 'residential',
            'active_model': None,
            'tariffs_ready': True,
        })
        self.assertIn('CEMIG-D', html)
        self.assertIn('SE/CO', html)


class AutomationContractTests(TestCase):
    def test_full_automation_stage_exists_and_runs_both_algorithms_all_regions(self):
        from web.studio.services.stage_registry import STAGE_MAP, build_command
        stage=STAGE_MAP['full_automation']
        self.assertTrue(stage.params)
        cmd=build_command('full_automation',{'start_year':'2023','end_year':'2026','climate_grid_mode':'adaptive','skip_operational':'1'})
        self.assertIn('scripts/47_run_full_automation.py',cmd)
        self.assertNotIn('--climate-year',cmd)
        self.assertIn('--climate-grid-mode',cmd)
        self.assertIn('--climate-daily-batch-size',cmd)
        self.assertIn('--climate-defer-wait-seconds',cmd)

    def test_regional_point_configs_exist(self):
        from django.conf import settings
        from pathlib import Path
        root=Path(settings.PREDICTA_PROJECT_ROOT)
        for tag in ['n','ne','seco','s']:
            self.assertTrue((root/f'configs/e2_{tag}_points.csv').exists(),tag)

    def test_automation_uses_multiyear_grid_climate_scripts(self):
        from pathlib import Path
        from django.conf import settings
        root=Path(settings.PREDICTA_PROJECT_ROOT)
        text=(root/'scripts/47_run_full_automation.py').read_text(encoding='utf-8')
        self.assertIn('52_build_climate_grid_points.py',text)
        self.assertIn('53_download_multiyear_grid_climate.py',text)
        self.assertIn('54_prepare_multiyear_e3.py',text)
        self.assertNotIn('--climate-year',text)
