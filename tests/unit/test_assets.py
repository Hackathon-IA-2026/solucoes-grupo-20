import pandas as pd
from motor_sin.assets.generation_assets import geocode_generation_assets
from motor_sin.assets.network import prepare_substations,prepare_transmission_lines,compute_hub_scores

def test_asset_geocode_and_hub_reproducible():
 gen=pd.DataFrame([{'plant_id':'p1','plant_name':'Usina A','generation_type':'SOLAR','subsystem_id':'SE/CO','state':'RJ'}])
 reg=pd.DataFrame([{'plant_id':'p1','plant_name':'Usina A','latitude':-22.9,'longitude':-43.2,'capacity_mw':50}])
 a=geocode_generation_assets(gen,reg); assert a.iloc[0].location_quality=='A'; assert a.iloc[0].cell_id.startswith('g01_')
 sub=prepare_substations(pd.DataFrame([{'substation_id':'s1','name':'S1','lat':-22.9,'lon':-43.2,'voltage_kv':500,'subsystem_id':'SE/CO','transformer_mva':1000},{'substation_id':'s2','name':'S2','lat':-23.0,'lon':-43.3,'voltage_kv':230,'subsystem_id':'SE/CO','transformer_mva':200}]))
 lines=prepare_transmission_lines(pd.DataFrame([{'line_id':'l1','from_substation':'s1','to_substation':'s2','voltage_kv':500}]),sub)
 h1=compute_hub_scores(sub,lines,{'transformer_mva':.4,'degree':.25,'max_kv':.25,'betweenness':.1}); h2=compute_hub_scores(sub,lines,{'transformer_mva':.4,'degree':.25,'max_kv':.25,'betweenness':.1})
 assert h1['hub_score'].tolist()==h2['hub_score'].tolist(); assert lines.iloc[0].geometry_quality=='SCHEMATIC'
