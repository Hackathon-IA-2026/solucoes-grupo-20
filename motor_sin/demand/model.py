from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Sequence
import numpy as np
import pandas as pd


@dataclass
class RidgeQuantileModel:
    features:list[str]
    mean_:np.ndarray
    scale_:np.ndarray
    coef_:np.ndarray
    intercept_:float
    residual_p10:float
    residual_p90:float
    ridge_alpha:float=1.0
    calibration_rows:int=0
    calibration_method:str='in_sample_residual_quantiles'
    target_interval_coverage:float=0.80
    calibration_empirical_coverage:float|None=None

    @property
    def algorithm(self) -> str:
        return 'ridge'

    def predict_p50(self,frame:pd.DataFrame)->np.ndarray:
        X=frame[self.features].astype(float).to_numpy();Z=(X-self.mean_)/self.scale_;return self.intercept_+Z@self.coef_
    def predict(self,frame:pd.DataFrame)->tuple[np.ndarray,np.ndarray,np.ndarray]:
        p50=self.predict_p50(frame);p10=np.maximum(0,p50+self.residual_p10);p90=np.maximum(p10,p50+self.residual_p90);p50=np.maximum(p10,np.minimum(p50,p90));return p10,p50,p90
    def to_dict(self)->dict:
        return {'model_type':'ridge_quantile_residual','features':self.features,'mean':self.mean_.tolist(),'scale':self.scale_.tolist(),'coef':self.coef_.tolist(),'intercept':self.intercept_,'residual_p10':self.residual_p10,'residual_p90':self.residual_p90,'ridge_alpha':self.ridge_alpha,'calibration_rows':self.calibration_rows,'calibration_method':self.calibration_method,'target_interval_coverage':self.target_interval_coverage,'calibration_empirical_coverage':self.calibration_empirical_coverage}
    @classmethod
    def from_dict(cls,p):return cls(list(p['features']),np.array(p['mean']),np.array(p['scale']),np.array(p['coef']),float(p['intercept']),float(p['residual_p10']),float(p['residual_p90']),float(p.get('ridge_alpha',1.0)),int(p.get('calibration_rows',0)),str(p.get('calibration_method','in_sample_residual_quantiles')),float(p.get('target_interval_coverage',0.80)),None if p.get('calibration_empirical_coverage') is None else float(p.get('calibration_empirical_coverage')))


@dataclass
class XGBoostResidualModel:
    """XGBoost point forecast with the same residual-quantile interval contract as Ridge.

    The point model uses squared-error boosting. P10/P90 are calibrated on a chronological
    holdout block outside point-model fitting, exactly like the Ridge path. This keeps interval
    semantics comparable while allowing a nonlinear model for the p50 forecast.
    """
    features:list[str]
    estimator:Any
    residual_p10:float
    residual_p90:float
    params:dict[str,Any]
    calibration_rows:int=0
    calibration_method:str='in_sample_residual_quantiles'
    target_interval_coverage:float=0.80
    calibration_empirical_coverage:float|None=None
    booster_file:str|None=None

    @property
    def algorithm(self) -> str:
        return 'xgboost'

    def predict_p50(self, frame:pd.DataFrame)->np.ndarray:
        X=frame[self.features].astype(float)
        return np.asarray(self.estimator.predict(X),dtype=float)

    def predict(self,frame:pd.DataFrame)->tuple[np.ndarray,np.ndarray,np.ndarray]:
        p50=self.predict_p50(frame);p10=np.maximum(0,p50+self.residual_p10);p90=np.maximum(p10,p50+self.residual_p90);p50=np.maximum(p10,np.minimum(p50,p90));return p10,p50,p90

    def to_dict(self)->dict:
        return {
            'model_type':'xgboost_residual_interval',
            'features':self.features,
            'residual_p10':float(self.residual_p10),
            'residual_p90':float(self.residual_p90),
            'params':self.params,
            'calibration_rows':int(self.calibration_rows),
            'calibration_method':self.calibration_method,
            'target_interval_coverage':float(self.target_interval_coverage),
            'calibration_empirical_coverage':self.calibration_empirical_coverage,
            'booster_file':self.booster_file,
        }


DemandModel = RidgeQuantileModel | XGBoostResidualModel


def fit_ridge_quantile(df:pd.DataFrame,features:Sequence[str],*,alpha:float=1.0)->RidgeQuantileModel:
    work=df.dropna(subset=[*features,'load_mw']).copy()
    if len(work)<max(30,len(features)+5):raise ValueError(f'not enough training rows: {len(work)}')
    X=work[list(features)].astype(float).to_numpy();y=work['load_mw'].astype(float).to_numpy();mean=X.mean(0);scale=X.std(0);scale=np.where(scale<1e-9,1.0,scale);Z=(X-mean)/scale;intercept=float(y.mean());yc=y-intercept;A=Z.T@Z+float(alpha)*np.eye(Z.shape[1]);coef=np.linalg.solve(A,Z.T@yc);pred=intercept+Z@coef;res=y-pred
    return RidgeQuantileModel(list(features),mean,scale,coef,intercept,float(np.quantile(res,.10)),float(np.quantile(res,.90)),float(alpha))


def default_xgboost_params() -> dict[str, Any]:
    return {
        'n_estimators': 350,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.9,
        'colsample_bytree': 0.9,
        'min_child_weight': 1.0,
        'reg_lambda': 1.0,
        'reg_alpha': 0.0,
        'objective': 'reg:squarederror',
        'tree_method': 'hist',
        'random_state': 42,
        'n_jobs': 2,
    }


def fit_xgboost_residual(df:pd.DataFrame,features:Sequence[str],*,params:dict[str,Any]|None=None)->XGBoostResidualModel:
    try:
        import sklearn  # noqa: F401 -- required by the XGBoost sklearn wrapper
        from xgboost import XGBRegressor
    except Exception as exc:
        raise RuntimeError('XGBoost requer xgboost + scikit-learn. Execute: pip install -e ".[ml]"') from exc
    work=df.dropna(subset=[*features,'load_mw']).copy()
    if len(work)<max(50,len(features)+10):raise ValueError(f'not enough training rows for xgboost: {len(work)}')
    cfg=default_xgboost_params(); cfg.update(params or {})
    est=XGBRegressor(**cfg)
    X=work[list(features)].astype(float); y=work['load_mw'].astype(float).to_numpy()
    est.fit(X,y,verbose=False)
    pred=np.asarray(est.predict(X),dtype=float);res=y-pred
    return XGBoostResidualModel(list(features),est,float(np.quantile(res,.10)),float(np.quantile(res,.90)),cfg)


def fit_demand_model(df:pd.DataFrame,features:Sequence[str],*,algorithm:str='ridge',alpha:float=1.0,xgb_params:dict[str,Any]|None=None)->DemandModel:
    algo=str(algorithm).strip().lower()
    if algo in {'ridge','ridgequantilemodel'}:
        return fit_ridge_quantile(df,features,alpha=alpha)
    if algo in {'xgb','xgboost'}:
        return fit_xgboost_residual(df,features,params=xgb_params)
    raise ValueError(f'unsupported demand algorithm: {algorithm}')


def save_model(model:DemandModel,path:str|Path)->None:
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(model,RidgeQuantileModel):
        path.write_text(json.dumps(model.to_dict(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return
    if isinstance(model,XGBoostResidualModel):
        booster_path=path.with_suffix('.ubj')
        model.estimator.save_model(booster_path)
        model.booster_file=booster_path.name
        path.write_text(json.dumps(model.to_dict(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return
    raise TypeError(type(model))


def load_model(path:str|Path)->DemandModel:
    path=Path(path);payload=json.loads(path.read_text(encoding='utf-8'));typ=payload.get('model_type')
    if typ=='ridge_quantile_residual' or ('coef' in payload and 'mean' in payload):
        return RidgeQuantileModel.from_dict(payload)
    if typ=='xgboost_residual_interval':
        try:
            import sklearn  # noqa: F401 -- required by the XGBoost sklearn wrapper
            from xgboost import XGBRegressor
        except Exception as exc:
            raise RuntimeError('Modelo XGBoost requer xgboost + scikit-learn. Execute: pip install -e ".[ml]"') from exc
        booster_file=payload.get('booster_file')
        if not booster_file: raise ValueError(f'xgboost model metadata lacks booster_file: {path}')
        est=XGBRegressor();est.load_model(path.parent/booster_file)
        return XGBoostResidualModel(
            features=list(payload['features']),estimator=est,
            residual_p10=float(payload['residual_p10']),residual_p90=float(payload['residual_p90']),
            params=dict(payload.get('params') or {}),calibration_rows=int(payload.get('calibration_rows',0)),
            calibration_method=str(payload.get('calibration_method','in_sample_residual_quantiles')),
            target_interval_coverage=float(payload.get('target_interval_coverage',0.80)),
            calibration_empirical_coverage=None if payload.get('calibration_empirical_coverage') is None else float(payload.get('calibration_empirical_coverage')),
            booster_file=booster_file,
        )
    raise ValueError(f'unsupported model_type={typ!r} in {path}')


def feature_contributions(model:DemandModel,row:pd.Series,top_n:int=5)->dict[str,float]:
    if isinstance(model,RidgeQuantileModel):
        vals=row[model.features].astype(float).to_numpy();contrib=((vals-model.mean_)/model.scale_)*model.coef_;idx=np.argsort(np.abs(contrib))[::-1][:top_n];return {model.features[i]:float(contrib[i]) for i in idx}
    if isinstance(model,XGBoostResidualModel):
        try:
            import xgboost as xgb
            X=pd.DataFrame([[float(row[c]) for c in model.features]],columns=model.features)
            contrib=np.asarray(model.estimator.get_booster().predict(xgb.DMatrix(X),pred_contribs=True))[0][:-1]
            idx=np.argsort(np.abs(contrib))[::-1][:top_n]
            return {model.features[i]:float(contrib[i]) for i in idx}
        except Exception:
            # Fallback: native gain importance, still explicit that this is not per-row SHAP.
            imp=getattr(model.estimator,'feature_importances_',np.zeros(len(model.features)))
            idx=np.argsort(np.abs(imp))[::-1][:top_n]
            return {model.features[i]:float(imp[i]) for i in idx}
    raise TypeError(type(model))
