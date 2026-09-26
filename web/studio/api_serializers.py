from rest_framework import serializers


class SimulationRequestSerializer(serializers.Serializer):
    cnpj = serializers.CharField(max_length=20)
    region = serializers.CharField(max_length=10)
    distributor = serializers.CharField(max_length=120)
    profile = serializers.CharField(max_length=120)
    monthly_kwh = serializers.FloatField(min_value=1)
    customer_type = serializers.ChoiceField(
        choices=('residential', 'commercial', 'industrial_flat'),
        default='residential',
    )
    mode = serializers.ChoiceField(choices=('replay', 'operational'), default='replay')
    replay_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    flexible_pct = serializers.FloatField(min_value=0, max_value=80, default=20)


class SimulationResponseSerializer(serializers.Serializer):
    customer = serializers.DictField()
    concession = serializers.DictField(allow_null=True)
    optimization = serializers.DictField()
    window = serializers.DictField()
    hourly = serializers.ListField(child=serializers.DictField())
    simulation_mode = serializers.CharField()
    display_timezone = serializers.CharField()
    simulation_scope_pt = serializers.CharField()
    reference_tariff_mean_rs_kwh = serializers.FloatField()
    dynamic_tariff_mean_rs_kwh = serializers.FloatField()
    reference_cost_24h_rs = serializers.FloatField()
    dynamic_cost_24h_rs = serializers.FloatField()
    difference_pct = serializers.FloatField()


class ApiErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SimulationOptionsSerializer(serializers.Serializer):
    region = serializers.CharField()
    mode = serializers.CharField()
    effective_date = serializers.CharField(allow_null=True)
    operational_status = serializers.DictField()
    replay_windows = serializers.ListField(child=serializers.DictField())
    simulation_available = serializers.BooleanField()
    display_timezone = serializers.CharField()
