import pandas as pd
from motor_sin.calendar.br_calendar import calendar_flags,easter_date,calendar_feature_frame


def test_movable_and_fixed_calendar_flags():
 ts=pd.Series(pd.to_datetime(['2025-03-04T12:00:00Z','2025-04-21T12:00:00Z','2025-11-20T12:00:00Z'],utc=True))
 f=calendar_flags(ts)
 assert f.iloc[0].carnival==1
 assert f.iloc[1].holiday_national==1
 assert f.iloc[2].holiday_national==1
 assert easter_date(2025).isoformat()=='2025-04-20'


def test_calendar_features_use_explicit_local_timezone():
 # 03:00 UTC is midnight in Sao Paulo in 2025. Behavioural hour must be 0, not 3.
 ts=pd.Series(pd.to_datetime(['2025-01-01T03:00:00Z'],utc=True))
 local=calendar_feature_frame(ts,timezone='America/Sao_Paulo')
 utc=calendar_feature_frame(ts,timezone='UTC')
 assert int(local.iloc[0].hour)==0
 assert int(utc.iloc[0].hour)==3
 assert int(local.iloc[0].holiday_national)==1
