import pandas as pd
from motor_sin.demand.features import attach_baseline_scores,aggregate_climate_to_zones

def test_phase3_scores_attach_and_aggregate():
 ts=pd.Timestamp('2025-01-01T00:00:00Z')
 climate=pd.DataFrame([{'interval_start_utc':ts,'cell_id':'a','temperature_2m':30.0,'precipitation':0.0,'wind_speed_10m':4.0,'solar_radiation':0.0}])
 scores=pd.DataFrame([
 {'interval_start_utc':ts,'cell_id':'a','variable':'temperature_2m','anomaly':4.0,'percentile':.98},
 {'interval_start_utc':ts,'cell_id':'a','variable':'precipitation','anomaly':0.0,'percentile':.2},
 {'interval_start_utc':ts,'cell_id':'a','variable':'wind_speed_10m','anomaly':1.0,'percentile':.7},
 {'interval_start_utc':ts,'cell_id':'a','variable':'solar_radiation','anomaly':0.0,'percentile':.1},
 ])
 wide=attach_baseline_scores(climate,scores)
 assert wide.iloc[0].temperature_anomaly==4.0
 assert wide.iloc[0].temperature_percentile==.98
 out=aggregate_climate_to_zones(wide,pd.DataFrame([{'cell_id':'a','subsystem_id':'SE/CO'}]))
 assert out.iloc[0].temperature_anomaly_mean==4.0
 assert out.iloc[0].temperature_percentile_mean==.98
