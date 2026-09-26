from django.urls import path

from .api import (
    DistributionAreasApi,
    ProfilesApi,
    SimulationApi,
    SimulationOptionsApi,
)

app_name = 'studio_api'

urlpatterns = [
    path('catalog/distribution-areas/', DistributionAreasApi.as_view(), name='distribution-areas'),
    path('catalog/profiles/', ProfilesApi.as_view(), name='profiles'),
    path('simulations/options/', SimulationOptionsApi.as_view(), name='simulation-options'),
    path('simulations/', SimulationApi.as_view(), name='simulations'),
]
