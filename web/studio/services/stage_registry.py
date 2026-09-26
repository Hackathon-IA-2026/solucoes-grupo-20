from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from django.conf import settings
from .artifacts import get_artifact, artifact_path

ROOT=Path(settings.PREDICTA_PROJECT_ROOT)

@dataclass(frozen=True)
class Param:
    name:str; label:str; kind:str='text'; default:str=''; help:str=''; choices:tuple[tuple[str,str],...]=(); required:bool=False

@dataclass(frozen=True)
class Stage:
    id:str; section:str; title:str; summary:str; explanation:str; why:str; script:str|None
    outputs:tuple[str,...]=(); requires:tuple[str,...]=(); params:tuple[Param,...]=(); command_builder:Callable|None=None


def _p(params,name,default=''):
    v=params.get(name,default);return str(v).strip() if v is not None else str(default)

def _script(name,*args):
    import sys
    return [sys.executable,f'scripts/{name}',*[str(x) for x in args if str(x)!='']]

def _tests_cmd(params,active=None):
    import sys;return [sys.executable,'-m','pytest','-q']

def _sync_ons_cmd(params,active=None):
    return _script('45_sync_ons_history.py','--start-year',_p(params,'start_year','2021'),'--end-year',_p(params,'end_year','2025'),'--source-timezone',_p(params,'source_timezone','America/Sao_Paulo'))

def _tariff_geo_cmd(params,active=None):
    return _script('44_prepare_tariff_geography.py')

def _xgb_args(params):
    return ['--n-estimators',_p(params,'n_estimators','350'),'--max-depth',_p(params,'max_depth','6'),'--learning-rate',_p(params,'learning_rate','0.05'),'--subsample',_p(params,'subsample','0.9'),'--colsample-bytree',_p(params,'colsample_bytree','0.9')]

def _validate_model_cmd(params,active=None):
    exp=_p(params,'experiment','E3').upper();algo=_p(params,'algorithm','ridge').lower()
    cmd=_script('46_validate_model.py','--experiment',exp,'--algorithm',algo,'--subsystem',_p(params,'subsystem','SE/CO'),'--test-hours',_p(params,'test_hours','720'),'--calibration-hours',_p(params,'calibration_hours','720'),'--alpha',_p(params,'alpha','1.0'))
    if _p(params,'climate_archive_url'):cmd+=['--climate-archive-url',_p(params,'climate_archive_url')]
    if _p(params,'history_start'):cmd+=['--history-start',_p(params,'history_start')]
    if _p(params,'history_end'):cmd+=['--history-end',_p(params,'history_end')]
    if algo=='xgboost':cmd+=_xgb_args(params)
    return cmd

def _train_cmd(params,active=None):
    exp=_p(params,'experiment','E3').upper();subsystem=_p(params,'subsystem','SE/CO');algo=_p(params,'algorithm','ridge').lower();cal=_p(params,'calibration_hours','720')
    tag=subsystem.replace('/','_').lower();model_dir=_p(params,'model_dir') or f'models/demand/{exp.lower()}_{algo}_{tag}_web_v1';family=_p(params,'model_family_id') or f'{exp}_{algo.upper()}_{tag.upper()}_WEB_V1'
    cmd=_script('43_train_model_family.py','--experiment',exp,'--algorithm',algo,'--subsystem',subsystem,'--calibration-hours',cal,'--alpha',_p(params,'alpha','1.0'),'--model-dir',model_dir,'--model-family-id',family)
    if _p(params,'train_start'):cmd+=['--train-start',_p(params,'train_start')]
    if _p(params,'train_end'):cmd+=['--train-end',_p(params,'train_end')]
    if algo=='xgboost':cmd+=_xgb_args(params)
    return cmd

def _full_automation_cmd(params,active=None):
    cmd=_script('47_run_full_automation.py','--start-year',_p(params,'start_year','2023'),'--end-year',_p(params,'end_year','2026'),'--test-hours',_p(params,'test_hours','720'),'--calibration-hours',_p(params,'calibration_hours','720'),'--alpha',_p(params,'alpha','1.0'),'--n-estimators',_p(params,'n_estimators','350'),'--max-depth',_p(params,'max_depth','6'),'--learning-rate',_p(params,'learning_rate','0.05'),'--subsample',_p(params,'subsample','0.9'),'--colsample-bytree',_p(params,'colsample_bytree','0.9'),'--climate-grid-mode',_p(params,'climate_grid_mode','adaptive'),'--climate-stride-cells',_p(params,'climate_stride_cells','20'),'--climate-history-mode',_p(params,'climate_history_mode','local-first'),'--climate-store-root',_p(params,'climate_store_root','data/climate_store'),'--climate-batch-size',_p(params,'climate_batch_size','6'),'--climate-daily-batch-size',_p(params,'climate_daily_batch_size','24'),'--climate-request-delay',_p(params,'climate_request_delay','2.0'),'--climate-max-retries',_p(params,'climate_max_retries','10'),'--climate-backoff',_p(params,'climate_backoff','10.0'),'--climate-cooldown-after-429',_p(params,'climate_cooldown_after_429','3'),'--climate-cooldown-seconds',_p(params,'climate_cooldown_seconds','90'),'--climate-defer-wait-seconds',_p(params,'climate_defer_wait_seconds','900'),'--climate-defer-cycles',_p(params,'climate_defer_cycles','8'),'--operational-issue',_p(params,'operational_issue','auto'),'--max-load-staleness-hours',_p(params,'max_load_staleness_hours','3'))
    if _p(params,'climate_archive_url'):cmd+=['--climate-archive-url',_p(params,'climate_archive_url')]
    if _p(params,'history_start'):cmd+=['--history-start',_p(params,'history_start')]
    if _p(params,'history_end'):cmd+=['--history-end',_p(params,'history_end')]
    if _p(params,'skip_tests','0') in {'1','true','on','yes'}:cmd+=['--skip-tests']
    if _p(params,'skip_operational','0') in {'1','true','on','yes'}:cmd+=['--skip-operational']
    return cmd

def _refresh_operational_cmd(params,active=None):
    cmd=_script('50_refresh_operational.py','--issue-time',_p(params,'issue_time','auto'),'--max-staleness-hours',_p(params,'max_load_staleness_hours','3'))
    if _p(params,'start_year'):cmd+=['--start-year',_p(params,'start_year')]
    return cmd


def _seed_climate_store_cmd(params,active=None):
    return _script('55_manage_climate_store.py','seed-existing','--store-root',_p(params,'climate_store_root','data/climate_store'),'--annual-archive-root','data/raw/climate/annual_archive')

def _update_climate_store_cmd(params,active=None):
    cmd=_script('56_update_climate_store.py','--start-year',_p(params,'start_year','2026'),'--end-year',_p(params,'end_year','2026'),'--store-root',_p(params,'climate_store_root','data/climate_store'),'--batch-size',_p(params,'climate_batch_size','6'),'--daily-batch-size',_p(params,'climate_daily_batch_size','24'),'--request-delay',_p(params,'climate_request_delay','2.0'),'--max-retries',_p(params,'climate_max_retries','10'),'--backoff',_p(params,'climate_backoff','10.0'),'--cooldown-after-429',_p(params,'climate_cooldown_after_429','3'),'--cooldown-seconds',_p(params,'climate_cooldown_seconds','90'))
    if _p(params,'climate_archive_url'):cmd+=['--archive-url',_p(params,'climate_archive_url')]
    return cmd

def _verify_climate_store_cmd(params,active=None):
    return _script('57_verify_climate_store.py','--start-year',_p(params,'start_year','2023'),'--end-year',_p(params,'end_year','2026'),'--store-root',_p(params,'climate_store_root','data/climate_store'))

AUTOMATION_PARAMS=(
    Param('start_year','Histórico: ano inicial','number','2023','ONS e clima histórico acompanham automaticamente esse período.'),
    Param('end_year','Histórico: ano final','number','2026','ONS e clima são recortados ao overlap realmente disponível.'),
    Param('climate_grid_mode','Grade climática','select','adaptive','adaptive = lattice 0,1° + células de todas as usinas; full = todas as células mapeadas do Brasil.',choices=(('adaptive','Adaptativa 0,1° + usinas'),('full','Full grid 0,1° (muito pesado)'))),
    Param('climate_history_mode','Histórico climático','select','local-first','local-first usa o Climate Store e baixa somente gaps; local-only nunca acessa API histórica.',choices=(('local-first','Local first · API somente para gaps'),('local-only','Local only · sem API histórica'))),
    Param('climate_store_root','Climate Store','text','data/climate_store','Diretório persistente; preserve entre versões.'),
    Param('climate_stride_cells','Passo da amostra regional','number','20','20 células = amostra regional a cada ~2°; células de usinas entram sempre.'),
    Param('history_start','Treino: início opcional','date','','Se vazio, usa todo o overlap elegível.'),
    Param('history_end','Treino: fim opcional','date','','Se vazio, usa o último dado elegível.'),
    Param('test_hours','Holdout por configuração (h)','number','720','30 dias finais para validação.'),
    Param('calibration_hours','Calibração p10–p90 (h)','number','720'),
    Param('alpha','Ridge alpha','number','1.0'),
    Param('n_estimators','XGBoost árvores','number','350'),
    Param('max_depth','XGBoost profundidade','number','6'),
    Param('learning_rate','XGBoost learning rate','number','0.05'),
    Param('subsample','XGBoost subsample','number','0.9'),
    Param('colsample_bytree','XGBoost colsample','number','0.9'),
    Param('climate_batch_size','Open-Meteo batch horário','number','6','Coordenadas por requisição para histórico horário.'),
    Param('climate_daily_batch_size','Open-Meteo batch diário','number','24','E3/baseline diário usa lotes maiores e mistura fusos na mesma requisição para reduzir o número de chamadas.'),
    Param('climate_archive_url','Endpoint histórico Open-Meteo','text','','Vazio = API pública. Para alto volume, use um endpoint local/self-hosted como http://127.0.0.1:8080/v1/archive.'),
    Param('climate_request_delay','Pausa entre batches (s)','number','2.0'),
    Param('climate_max_retries','Retries HTTP 429/5xx','number','10'),
    Param('climate_backoff','Backoff inicial (s)','number','10.0'),
    Param('climate_cooldown_after_429','429 consecutivos antes do cooldown','number','3'),
    Param('climate_cooldown_seconds','Cooldown global (s)','number','90','Depois do limiar de 429, pausa o processo inteiro antes de continuar.'),
    Param('climate_defer_wait_seconds','Espera após quota persistente (s)','number','900','Se o 429 persistir após todos os retries, preserva checkpoint e retoma automaticamente depois desta espera.'),
    Param('climate_defer_cycles','Máx. ciclos automáticos de retomada','number','8','Depois disso a execução para como aguardando quota; repetir o botão retoma do cache.'),
    Param('operational_issue','Issue operacional','text','auto','auto = última hora ONS comum aos 4 subsistemas.'),
    Param('max_load_staleness_hours','Máx. defasagem ONS (h)','number','3','Publicação operacional é bloqueada se a carga estiver mais velha.'),
    Param('skip_tests','Pular testes automatizados','checkbox','0'),
    Param('skip_operational','Treinar sem publicar operacional agora','checkbox','0'),
)

def _forecast_active(params,active=None):
    if not active or not active.get('model_dir'):raise ValueError('Selecione um modelo ativo na página Modelos antes de executar a inferência.')
    issue=_p(params,'issue_time');
    if not issue:raise ValueError('issue_time é obrigatório')
    cmd=_script('38_forecast_frozen_e3.py','--model-dir',active['model_dir'],'--issue-time',issue,'--output','data/processed/demand/selected_forecast_24h.parquet','--report','outputs/reports/selected_model_inference.json')
    experiment=str(active.get('experiment','E3')).upper()
    if experiment in {'E2','E3'}:
        climate='data/processed/climate/zone_climate_hourly_e3.parquet' if experiment=='E3' else 'data/processed/climate/zone_climate_hourly.parquet';cmd+=['--climate',climate,'--allow-perfect-weather']
    return cmd

SUBSYSTEM_CHOICES=(('SE/CO','SE/CO'),('N','N'),('NE','NE'),('S','S'))
EXPERIMENT_CHOICES=(('E1','E1 · histórico + calendário'),('E2','E2 · + clima bruto'),('E3','E3 · + anomalias/eventos'))
ALGORITHM_CHOICES=(('ridge','Ridge · baseline linear'),('xgboost','XGBoost · árvores não lineares'))
MODEL_PARAMS=(
    Param('experiment','Features/experimento','select','E3',choices=EXPERIMENT_CHOICES),Param('algorithm','Algoritmo','select','ridge',choices=ALGORITHM_CHOICES),Param('subsystem','Subsistema','select','SE/CO',choices=SUBSYSTEM_CHOICES),
    Param('history_start','Início do histórico','date','','Opcional. Ex.: 2022-01-01'),Param('history_end','Fim do histórico','date','','Opcional. Deixe vazio para usar o último dado.'),
    Param('test_hours','Holdout de teste (h)','number','720','720 h = 30 dias finais.'),Param('calibration_hours','Calibração p10–p90 (h)','number','720'),Param('alpha','Ridge alpha','number','1.0','Usado apenas no Ridge.'),
    Param('n_estimators','XGB árvores','number','350'),Param('max_depth','XGB profundidade','number','3'),Param('learning_rate','XGB learning rate','number','0.05'),Param('subsample','XGB subsample','number','0.9'),Param('colsample_bytree','XGB colsample','number','0.9'),
)

STAGES=[
    Stage('full_automation','0 · Automação','Executar Predicta completo','Um único comando prepara ONS, grade climática 0,1°, clima multi-ano com baseline rolling, tarifas, valida Ridge/XGBoost em N/NE/SE-CO/S, congela modelos, seleciona o menor WAPE e tenta publicar o operacional H01–H24.','Orquestra todo o fluxo reproduzível do MVP sem exigir que o usuário conheça a ordem dos scripts.','É o caminho recomendado para reconstruir o ambiente do zero ou refazer todo o ciclo de ciência + deployment.',None,command_builder=_full_automation_cmd,params=AUTOMATION_PARAMS),
    Stage('refresh_operational','0 · Automação','Atualizar operacional 24h','Atualiza ONS, baixa nova previsão meteorológica, roda os modelos regionais selecionados e republica system_signal_v1.','Não retreina. Usa o registry vencedor produzido pela automação completa.','É o job rápido que deve rodar de forma recorrente após o treinamento.',None,command_builder=_refresh_operational_cmd,params=(Param('start_year','Histórico ONS: ano inicial','number','2021'),Param('issue_time','Issue time','text','auto'),Param('max_load_staleness_hours','Máx. defasagem ONS (h)','number','3'))),
    Stage('seed_climate_store','0 · Automação','Migrar cache para Climate Store','Reaproveita arquivos históricos já baixados sem internet.','Cria hardlinks/cópias em data/climate_store.','Seguro rodar várias vezes.',None,command_builder=_seed_climate_store_cmd,params=(Param('climate_store_root','Climate Store','text','data/climate_store'),)),
    Stage('update_climate_store','0 · Automação','Atualizar Climate Store','Consulta local primeiro e solicita somente datas/células ausentes.','Atualiza o histórico sem refazer dez anos de chamadas.','Depois do backfill, normalmente baixa apenas novos dias.',None,command_builder=_update_climate_store_cmd,params=(Param('start_year','Ano-alvo inicial','number','2026'),Param('end_year','Ano-alvo final','number','2026'),Param('climate_store_root','Climate Store','text','data/climate_store'),Param('climate_batch_size','Batch horário','number','6'),Param('climate_daily_batch_size','Batch diário','number','24'),Param('climate_archive_url','Endpoint histórico','text',''),Param('climate_request_delay','Pausa entre batches','number','2.0'),Param('climate_max_retries','Retries','number','10'),Param('climate_backoff','Backoff','number','10.0'),Param('climate_cooldown_after_429','429 antes cooldown','number','3'),Param('climate_cooldown_seconds','Cooldown','number','90'))),
    Stage('verify_climate_store','0 · Automação','Verificar Climate Store','Valida se E2, E3 e baselines podem ser reconstruídos sem internet histórica.','Calcula gaps por célula/data sem chamadas externas.','Use antes de mudar para local-only.',None,command_builder=_verify_climate_store_cmd,params=(Param('start_year','Ano inicial','number','2023'),Param('end_year','Ano final','number','2026'),Param('climate_store_root','Climate Store','text','data/climate_store'))),
    Stage('test_suite','0 · Ambiente','Rodar testes automatizados','Executa a suíte pytest.','Valida contratos, anti-leakage, features, clima, tarifa e integrações.','É o primeiro gate antes de confiar em uma alteração.',None,command_builder=_tests_cmd),
    Stage('bootstrap_contracts','0 · Ambiente','Validar contratos v1','Regenera e valida os contratos.','Confere grid_state_v1, asset_exposure_v1, system_signal_v1 e tariff_v1.','Mantém motores e web desacoplados.','00_bootstrap_phase0.py'),
    Stage('build_grid','0 · Ambiente','Construir grade 0,1°','Materializa a grade espacial canônica.','Cria cell_id em EPSG:4326.','Índice comum para clima/ativos.','01_build_grid.py',outputs=('grid',)),

    Stage('sync_ons_history','1 · Dados','Adicionar/consolidar anos ONS','Baixa os anos ausentes e reconstrói o histórico horário único.','Você escolhe um intervalo de anos. RAW existente é reutilizado; novos anos são acrescentados e o arquivo canônico é refeito sem duplicatas.','É aqui que você aumenta o histórico antes de um novo ciclo de treino.',None,outputs=('load','supply'),command_builder=_sync_ons_cmd,params=(Param('start_year','Ano inicial','number','2021'),Param('end_year','Ano final','number','2025'),Param('source_timezone','Timezone ONS','text','America/Sao_Paulo'))),
    Stage('prepare_tariff_geo','1 · Dados','Carregar mapa + tarifas ANEEL','Relaciona áreas reais de concessão às tarifas por CNPJ.','Usa o GeoJSON SIGEL/ANEEL em WGS84 e o CSV completo de tarifas homologadas incluído em references/. Filtra Tarifa de Aplicação e componentes volumétricos.','Habilita mapa real → distribuidora → perfil → TE+TUSD.',None,outputs=('base_tariffs','distributor_catalog','distributor_geo'),command_builder=_tariff_geo_cmd),
    Stage('data_gate','1 · Dados','Gate de qualidade','Valida continuidade e duplicidades.','Impede que treino prossiga com série desalinhada.','Qualidade de dado é separada de qualidade de modelo.','27_real_data_gate.py',requires=('load',),params=(Param('subsystem','Subsistema','select','SE/CO',choices=SUBSYSTEM_CHOICES),Param('with_climate','Validar clima E3 também','checkbox','0'))),

    Stage('download_e2','2 · Features climáticas','Baixar clima E2','Baixa clima horário do ano-alvo.','ERA5-Seamless para o piloto PERFECT_WEATHER_BACKTEST.','Prepara temperatura, precipitação, vento e radiação do horário-alvo.','31_download_e2_climate.py',requires=('load',),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),)),
    Stage('prepare_e2','2 · Features climáticas','Preparar E2','Agrega clima ao subsistema.','Materializa médias, medianas, p90 e máximos.','Forma a camada de clima bruto.','32_prepare_e2_zone_climate.py',outputs=('climate_e2',),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),Param('run_id','Run ID','text','e2-web'))),
    Stage('download_e3','2 · Features climáticas','Baixar baseline E3','Baixa 10 anos de baseline térmico e contexto diário.','Preserva as regras do snapshot OpenMeteo.','Permite medir anomalias e eventos.','34_download_e3_context.py',requires=('load',),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),Param('target_year','Ano-alvo','number','2025'))),
    Stage('prepare_e3','2 · Features climáticas','Construir E3','Calcula anomalias e eventos.','Combina E2 com baseline 10 anos e regras de calor/frio/chuva/vento.','É a feature set completa do MVP.','35_prepare_e3_context.py',requires=('climate_e2',),outputs=('climate_e3','climate_baseline','e3_daily'),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),Param('target_year','Ano-alvo','number','2025'))),

    Stage('validate_model','3 · Modelagem','Treinar + validar configuração','Executa backtest de uma configuração Ridge ou XGBoost.','Treina 24 modelos direct H01–H24 usando o experimento selecionado e avalia no holdout cronológico.','Aqui você compara algoritmo, features e janela histórica antes de congelar o modelo.',None,requires=('load',),command_builder=_validate_model_cmd,params=MODEL_PARAMS),
    # Legacy scientific comparison kept available for reproducing the E0→E3 experiment exactly.
    Stage('validate_e1','3 · Modelagem','Reproduzir E0/E1 Ridge','Reexecuta o experimento histórico E0/E1.','Backtest fixed-origin com Ridge.','Reprodutibilidade do piloto.','29_run_real_pilot.py',requires=('load',),params=(Param('subsystem','Subsistema','select','SE/CO',choices=SUBSYSTEM_CHOICES),Param('test_hours','Horas de teste','number','720'),Param('calibration_hours','Calibração','number','720'))),
    Stage('validate_e2','3 · Modelagem','Reproduzir E2 Ridge','Reexecuta E1/E2.','Mesmo holdout e Ridge.','Reprodutibilidade do piloto climático.','33_run_e2.py',requires=('load','climate_e2'),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),Param('test_hours','Horas de teste','number','720'),Param('calibration_hours','Calibração','number','720'))),
    Stage('validate_e3','3 · Modelagem','Reproduzir E0–E3 Ridge','Reexecuta a comparação final do piloto.','Mesmo holdout e Ridge para isolar features.','Reprodutibilidade da evidência apresentada.','36_run_e3.py',requires=('load','climate_e3'),outputs=('metrics_e3','predictions_e3'),params=(Param('subsystem','Subsistema','select','SE/CO',choices=(('SE/CO','SE/CO'),)),Param('test_hours','Horas de teste','number','720'),Param('calibration_hours','Calibração','number','720'))),

    Stage('train_model','4 · Deployment','Treinar/congelar H01–H24','Empacota a configuração escolhida para inferência.','Usa histórico elegível e reserva a cauda para calibrar intervalos.','Só deve ser feito depois da validação.',None,requires=('load',),command_builder=_train_cmd,params=MODEL_PARAMS + (Param('train_start','Treino: início','date',''),Param('train_end','Treino: fim','date',''),Param('model_family_id','ID da família','text',''),Param('model_dir','Diretório','text',''))),
    Stage('forecast_active','4 · Deployment','Inferir com modelo ativo','Gera H01–H24 sem retreino.','Reconstrói as mesmas features e carrega os artefatos congelados.','É o comportamento operacional esperado no Django.',None,command_builder=_forecast_active,requires=('load',),params=(Param('issue_time','Issue time UTC','text','2025-12-30T02:00:00Z'),)),
    Stage('build_signal','4 · Deployment','Construir system_signal_v1','Transforma forecast em contrato do Motor 1.','Publica p10/p50/p90, D, C, drivers e qualidade.','É a entrada única do Motor 2.','39_build_real_system_signal.py',outputs=('system_signal',),params=(Param('use_selected_forecast','Usar forecast do modelo ativo','checkbox','1'),)),
]
STAGE_MAP={s.id:s for s in STAGES}


def _default_cmd(stage:Stage,params:dict,active=None):
    if stage.command_builder:return stage.command_builder(params,active)
    sid=stage.id
    if sid=='bootstrap_contracts':return _script(stage.script,'--require-parquet')
    if sid=='build_grid':return _script(stage.script,'--brazil-only','--output','data/processed/grid/brazil_grid_01deg.parquet')
    if sid=='data_gate':
        cmd=_script(stage.script,'--load','data/processed/demand/load_hourly.parquet','--subsystem',_p(params,'subsystem','SE/CO'),'--weather-mode','PERFECT_WEATHER_BACKTEST')
        if _p(params,'with_climate','0') in {'1','true','on','yes'}:cmd+=['--climate','data/processed/climate/zone_climate_hourly_e3.parquet']
        return cmd
    if sid=='download_e2':return _script(stage.script,'--load','data/processed/demand/load_hourly.parquet','--subsystem',_p(params,'subsystem','SE/CO'),'--model','era5_seamless')
    if sid=='prepare_e2':return _script(stage.script,'--subsystem',_p(params,'subsystem','SE/CO'),'--run-id',_p(params,'run_id','e2-web'))
    if sid=='download_e3':return _script(stage.script,'--load','data/processed/demand/load_hourly.parquet','--subsystem',_p(params,'subsystem','SE/CO'),'--target-year',_p(params,'target_year','2025'))
    if sid=='prepare_e3':return _script(stage.script,'--subsystem',_p(params,'subsystem','SE/CO'),'--target-year',_p(params,'target_year','2025'))
    if sid=='validate_e1':return _script(stage.script,'--load','data/processed/demand/load_hourly.parquet','--subsystem',_p(params,'subsystem','SE/CO'),'--weather-mode','PERFECT_WEATHER_BACKTEST','--test-hours',_p(params,'test_hours','720'),'--forecast-horizon','24','--origin-step-hours','24','--calendar-timezone','America/Sao_Paulo','--calibration-hours',_p(params,'calibration_hours','720'))
    if sid=='validate_e2':return _script(stage.script,'--subsystem',_p(params,'subsystem','SE/CO'),'--test-hours',_p(params,'test_hours','720'),'--calibration-hours',_p(params,'calibration_hours','720'))
    if sid=='validate_e3':return _script(stage.script,'--subsystem',_p(params,'subsystem','SE/CO'),'--test-hours',_p(params,'test_hours','720'),'--calibration-hours',_p(params,'calibration_hours','720'))
    if sid=='build_signal':
        cmd=_script(stage.script)
        if _p(params,'use_selected_forecast','1') in {'1','true','on','yes'} and (ROOT/'data/processed/demand/selected_forecast_24h.parquet').exists():cmd+=['--forecast','data/processed/demand/selected_forecast_24h.parquet']
        return cmd
    raise KeyError(stage.id)

def build_command(stage_id:str,params:dict,active=None):
    stage=STAGE_MAP.get(stage_id)
    if not stage:raise KeyError(f'Etapa desconhecida: {stage_id}')
    return _default_cmd(stage,params,active)

def stage_status(stage:Stage):
    required=[]
    for k in stage.requires:
        a=get_artifact(k);required.append({'key':k,'label':a.label if a else k,'exists':bool(a and artifact_path(a).exists())})
    outputs=[]
    for k in stage.outputs:
        a=get_artifact(k);outputs.append({'key':k,'label':a.label if a else k,'exists':bool(a and artifact_path(a).exists())})
    status='DONE' if stage.outputs and all(x['exists'] for x in outputs) else ('BLOCKED' if any(not x['exists'] for x in required) else 'READY')
    return {'status':status,'required':required,'outputs':outputs}

def stage_sections():
    sections=[]
    for stage in STAGES:
        sec=next((s for s in sections if s['name']==stage.section),None)
        if sec is None:sec={'name':stage.section,'stages':[]};sections.append(sec)
        sec['stages'].append({'stage':stage,**stage_status(stage)})
    return sections
