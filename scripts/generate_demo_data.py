#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_sin.grid.index import coordinate_to_index
from motor_sin.common.io import write_table

ZONES={'N':(-3.1,-60.0,7200),'NE':(-8.1,-35.0,14500),'S':(-25.4,-51.2,12000),'SE/CO':(-22.9,-43.2,42000)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--issue-time',default='2026-09-19T00:00:00Z');p.add_argument('--root',default='data/demo');a=p.parse_args();root=Path(a.root);root.mkdir(parents=True,exist_ok=True);issue=pd.Timestamp(a.issue_time)
 if issue.tzinfo is None:issue=issue.tz_localize('UTC')
 else:issue=issue.tz_convert('UTC')
 # Cell map: two cells per subsystem.
 maps=[]
 for z,(lat,lon,_) in ZONES.items():
  for dlat,dlon in [(0,0),(.12,.12)]:maps.append({'cell_id':coordinate_to_index(lat+dlat,lon+dlon).cell_id,'subsystem_id':z,'lat':lat+dlat,'lon':lon+dlon})
 cellmap=pd.DataFrame(maps);write_table(cellmap,root/'cell_subsystem_map.csv')
 # Historical load + climate and future climate.
 hist_start=issue-pd.Timedelta(days=100);times=pd.date_range(hist_start,issue,freq='h',inclusive='both');cl=[];ld=[]
 rng=np.random.default_rng(42)
 for z,(lat,lon,base) in ZONES.items():
  phase={'N':1,'NE':2,'S':3,'SE/CO':4}[z]
  for i,ts in enumerate(times):
   hour=ts.hour;temp=24+6*np.sin((hour-10)/24*2*np.pi)+phase+rng.normal(0,.5);solar=max(0,800*np.sin((hour-6)/12*np.pi));wind=3+1.5*np.sin((hour+phase)/24*2*np.pi);rain=max(0,rng.normal(.2,.8));inc=max(0,(temp-31)/8)
   cl.append({'interval_start_utc':ts,'subsystem_id':z,'temperature_2m_mean':temp,'temperature_2m_median':temp,'temperature_2m_p90':temp+1,'temperature_2m_max':temp+2,'precipitation_mean':rain,'precipitation_median':rain,'precipitation_p90':rain*2,'precipitation_max':rain*3,'wind_speed_10m_mean':wind,'wind_speed_10m_median':wind,'wind_speed_10m_p90':wind+1,'wind_speed_10m_max':wind+2,'solar_radiation_mean':solar,'solar_radiation_median':solar,'solar_radiation_p90':solar*1.05,'solar_radiation_max':solar*1.1,'temperature_anomaly_mean':temp-26,'incident_cell_fraction':min(1,inc),'weighting_method':'uniform'})
   load=base*(1+.10*np.sin((hour-13)/24*2*np.pi)+.006*(temp-25)+.03*(ts.dayofweek<5))+rng.normal(0,base*.01);ld.append({'interval_start_utc':ts,'subsystem_id':z,'load_mw':max(0,load)})
 future_times=pd.date_range(issue+pd.Timedelta(hours=1),periods=24,freq='h')
 for z,(lat,lon,base) in ZONES.items():
  phase={'N':1,'NE':2,'S':3,'SE/CO':4}[z]
  for ts in future_times:
   hour=ts.hour;temp=25+7*np.sin((hour-10)/24*2*np.pi)+phase;solar=max(0,800*np.sin((hour-6)/12*np.pi));wind=3+1.5*np.sin((hour+phase)/24*2*np.pi);rain=max(0,.5*np.sin(hour));inc=max(0,(temp-31)/8)
   cl.append({'interval_start_utc':ts,'subsystem_id':z,'temperature_2m_mean':temp,'temperature_2m_median':temp,'temperature_2m_p90':temp+1,'temperature_2m_max':temp+2,'precipitation_mean':rain,'precipitation_median':rain,'precipitation_p90':rain*2,'precipitation_max':rain*3,'wind_speed_10m_mean':wind,'wind_speed_10m_median':wind,'wind_speed_10m_p90':wind+1,'wind_speed_10m_max':wind+2,'solar_radiation_mean':solar,'solar_radiation_median':solar,'solar_radiation_p90':solar*1.05,'solar_radiation_max':solar*1.1,'temperature_anomaly_mean':temp-26,'incident_cell_fraction':min(1,inc),'weighting_method':'uniform'})
 write_table(pd.DataFrame(ld),root/'load_hourly.parquet');write_table(pd.DataFrame(cl),root/'zone_climate.parquet')
 # Target cell-level scores for phase 4/12.
 rows=[]
 for m in maps:
  z=m['subsystem_id'];phase={'N':1,'NE':2,'S':3,'SE/CO':4}[z]
  for ts in future_times:
   hour=ts.hour;temp=25+7*np.sin((hour-10)/24*2*np.pi)+phase;solar=max(0,800*np.sin((hour-6)/12*np.pi));wind=3+1.5*np.sin((hour+phase)/24*2*np.pi);rain=max(0,.5*np.sin(hour))
   values={'temperature_2m':temp,'precipitation':rain,'wind_speed_10m':wind,'solar_radiation':solar,'dewpoint_2m':temp-4}
   pcts={'temperature_2m':float(np.clip(.5+(temp-27)/15,0,1)),'precipitation':.99 if rain>.4 else .5,'wind_speed_10m':.97 if wind>4 else .5,'solar_radiation':.03 if solar>0 and hour in [9,10] else .5,'dewpoint_2m':.5}
   for var,v in values.items():rows.append({'baseline_version':'1.0','target_year':ts.year,'baseline_year_start':ts.year-10,'baseline_year_end':ts.year-1,'interval_start_utc':ts,'cell_id':m['cell_id'],'variable':var,'value':v,'baseline_median':26 if var=='temperature_2m' else 0,'baseline_iqr':4,'anomaly':v-(26 if var=='temperature_2m' else 0),'robust_z':0,'percentile':pcts[var],'baseline_sample_count':300,'expected_sample_count':310,'coverage_ratio':.97})
 write_table(pd.DataFrame(rows),root/'target_scores.parquet')
 # Generation raw canonical + registry.
 gens=[];reg=[]
 types={'N':'HIDROELÉTRICA','NE':'EOLIELÉTRICA','S':'HIDROELÉTRICA','SE/CO':'FOTOVOLTAICA'}
 for z,(lat,lon,base) in ZONES.items():
  pid='PLANT_'+z.replace('/','_');reg.append({'plant_id':pid,'plant_name':'Usina '+z,'latitude':lat,'longitude':lon,'capacity_mw':base*.75})
  for ts in future_times:gens.append({'interval_start_utc':ts,'plant_id':pid,'plant_name':'Usina '+z,'generation_type':types[z],'subsystem_id':z,'state':'XX','generation_mw':base*.82})
 write_table(pd.DataFrame(gens),root/'generation_hourly.parquet');write_table(pd.DataFrame(reg),root/'generation_registry.csv')
 # Substations + lines.
 subs=[]
 for z,(lat,lon,base) in ZONES.items():subs.append({'substation_id':'SUB_'+z.replace('/','_'),'name':'Sub '+z,'lat':lat+.12,'lon':lon+.12,'voltage_kv':500 if z=='SE/CO' else 230,'subsystem_id':z,'transformer_mva':base/10})
 write_table(pd.DataFrame(subs),root/'substations.csv')
 lines=[];ids=[x['substation_id'] for x in subs]
 for i in range(len(ids)-1):lines.append({'line_id':f'LINE_{i+1}','from_substation':ids[i],'to_substation':ids[i+1],'voltage_kv':500 if i==2 else 230,'geometry_quality':'SCHEMATIC'})
 write_table(pd.DataFrame(lines),root/'lines.csv')
 # tariff and consumption.
 tariff=pd.DataFrame([{'distributor_id':'DIST_EXAMPLE_SECO','tariff_profile_id':'B1_CONVENTIONAL_FIXTURE','tariff_post':'UNIQUE','base_te_rs_kwh':.31,'base_tusd_rs_kwh':.44,'base_total_rs_kwh':.75,'valid_from':'2026-01-01','valid_to':'2026-12-31','source':'synthetic_fixture_not_regulatory'}]);write_table(tariff,root/'base_tariffs.csv')
 consumption=pd.DataFrame({'interval_start_utc':future_times,'consumption_kwh':[100+30*(17<=ts.hour<=21) for ts in future_times]});write_table(consumption,root/'consumption_profile.csv')
 print(f'demo_root={root.resolve()} issue_time={issue.isoformat()}')
if __name__=='__main__':main()
