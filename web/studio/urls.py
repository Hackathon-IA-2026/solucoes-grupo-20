from django.urls import path
from . import views

app_name='studio'
urlpatterns=[
    path('',views.dashboard,name='dashboard'),
    path('automacao/',views.automation_page,name='automation'),
    path('dados/',views.data_explorer,name='data'),
    path('features/',views.features_page,name='features'),
    path('territorio/',views.territory_page,name='territory'),
    path('modelagem/',views.modeling_page,name='modeling'),
    path('validacao/',views.validation_page,name='validation'),
    path('experimentos/',views.experiments,name='experiments'),
    path('modelos/',views.models_page,name='models'),
    path('modelos/ativar/',views.activate_model,name='activate_model'),
    path('produto/',views.product,name='product'),
    path('pipeline/',views.pipeline,name='pipeline'),
    path('pipeline/run/<str:stage_id>/',views.run_stage,name='run_stage'),
    path('runs/<uuid:run_id>/',views.run_detail,name='run_detail'),
    path('api/runs/<uuid:run_id>/',views.run_status,name='run_status'),
    path('api/tariff-profiles/',views.api_profiles,name='api_profiles'),
    path('api/distribution-areas/',views.api_distribution_areas,name='api_distribution_areas'),
    path('api/distributor-info/',views.api_distributor_info,name='api_distributor_info'),
]
