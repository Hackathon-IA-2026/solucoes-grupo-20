from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import (
    ApiErrorSerializer,
    SimulationOptionsSerializer,
    SimulationRequestSerializer,
    SimulationResponseSerializer,
)
from .services.distribution import (
    distributor_info,
    geojson_payload,
    tariff_profiles_for_cnpj,
)
from .services.product import (
    DISPLAY_TIMEZONE,
    available_regions,
    effective_date_for,
    operational_status,
    replay_windows,
    simulate_customer,
    simulation_available,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if pd.isna(value) if not isinstance(value, (str, bytes, bool, dict, list, tuple, set)) else False:
        return None
    return value


def _hourly_payload(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dict(orient='records'):
        item = _json_value(row)
        timestamp = pd.Timestamp(item['interval_start_utc']).tz_convert(DISPLAY_TIMEZONE)
        flags = item.get('quality_flags', [])
        if isinstance(flags, str):
            try:
                import json
                flags = json.loads(flags)
            except ValueError:
                flags = [flags]
        context = 'HOUR_MONTH'
        reference_n = None
        for flag in flags or []:
            flag = str(flag)
            if flag.startswith('DEMAND_PERCENTILE_CONTEXT_'):
                context = flag.replace('DEMAND_PERCENTILE_CONTEXT_', '')
            if flag.startswith('DEMAND_PERCENTILE_REFERENCE_N_'):
                try:
                    reference_n = int(flag.replace('DEMAND_PERCENTILE_REFERENCE_N_', ''))
                except ValueError:
                    pass
        base = float(item['base_total_rs_kwh'])
        dynamic = float(item['dynamic_tariff_rs_kwh'])
        rows.append({
            'interval_start_utc': item['interval_start_utc'],
            'local_iso': timestamp.isoformat(),
            'time': timestamp.strftime('%d/%m %Hh'),
            'base_rs_kwh': base,
            'dynamic_rs_kwh': dynamic,
            'consumption_kwh': float(item['consumption_kwh']),
            'optimized_consumption_kwh': float(item['optimized_consumption_kwh']),
            'multiplier': float(item['final_multiplier']),
            'demand_pressure': float(item['demand_pressure']),
            'demand_p50_mw': float(item['demand_p50_mw']),
            'demand_context': context,
            'demand_reference_n': reference_n,
            'delta_pct': 100 * (dynamic / base - 1) if base else 0,
        })
    return rows


class DistributionAreasApi(APIView):
    @extend_schema(
        tags=['Catálogo'],
        responses={200: OpenApiResponse(description='GeoJSON das áreas de concessão')},
    )
    def get(self, request):
        return Response(geojson_payload())


class ProfilesApi(APIView):
    @extend_schema(
        tags=['Catálogo'],
        parameters=[
            OpenApiParameter('cnpj', str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('region', str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('mode', str, OpenApiParameter.QUERY, enum=['replay', 'operational'], required=False),
            OpenApiParameter('replay_issue', str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('effective_date', str, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description='Distribuidora e perfis tarifários')},
    )
    def get(self, request):
        cnpj = request.query_params.get('cnpj', '')
        region = request.query_params.get('region') or None
        mode = request.query_params.get('mode', 'replay')
        replay_key = request.query_params.get('replay_issue') or None
        if mode not in {'replay', 'operational'}:
            return Response({'detail': 'mode deve ser replay ou operational.'}, status=status.HTTP_400_BAD_REQUEST)
        effective_raw = request.query_params.get('effective_date')
        effective = None
        if effective_raw:
            try:
                effective = date.fromisoformat(effective_raw)
            except ValueError:
                return Response({'detail': 'effective_date deve estar em YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        if effective is None and region:
            effective = effective_date_for(region, mode, replay_key)
        return Response({
            'distributor': _json_value(distributor_info(cnpj)),
            'profiles': _json_value(tariff_profiles_for_cnpj(cnpj, region, effective_date=effective)),
            'display_timezone': DISPLAY_TIMEZONE,
        })


class SimulationOptionsApi(APIView):
    @extend_schema(
        tags=['Simulação'],
        parameters=[
            OpenApiParameter('region', str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('mode', str, OpenApiParameter.QUERY, enum=['replay', 'operational']),
        ],
        responses={200: SimulationOptionsSerializer},
    )
    def get(self, request):
        region = request.query_params.get('region', '')
        mode = request.query_params.get('mode', 'replay')
        if mode not in {'replay', 'operational'}:
            return Response({'detail': 'mode deve ser replay ou operational.'}, status=status.HTTP_400_BAD_REQUEST)
        replay_key = request.query_params.get('replay_key') or None
        return Response({
            'region': region,
            'mode': mode,
            'effective_date': (effective_date_for(region, mode, replay_key).isoformat()
                               if effective_date_for(region, mode, replay_key) else None),
            'operational_status': operational_status(region),
            'replay_windows': replay_windows(region),
            'simulation_available': simulation_available(region, mode, replay_key),
            'display_timezone': DISPLAY_TIMEZONE,
            'regions': [{'id': key, 'available': value} for key, value in available_regions().items()],
        })


class SimulationApi(APIView):
    @extend_schema(
        tags=['Simulação'],
        request=SimulationRequestSerializer,
        responses={
            200: SimulationResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, description='Payload inválido ou simulação indisponível'),
        },
    )
    def post(self, request):
        serializer = SimulationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            result, frame = simulate_customer(
                region=payload['region'],
                cnpj=payload['cnpj'],
                distributor=payload['distributor'],
                profile=payload['profile'],
                monthly_kwh=payload['monthly_kwh'],
                customer_type=payload['customer_type'],
                mode=payload['mode'],
                replay_key=payload.get('replay_key') or None,
                flexible_fraction=payload['flexible_pct'] / 100,
            )
        except (ValueError, KeyError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = _json_value(result)
        response['hourly'] = _hourly_payload(frame)
        return Response(response)
