from django.test import TestCase
from rest_framework.test import APIClient


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
