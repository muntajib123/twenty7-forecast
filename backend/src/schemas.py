from pydantic import BaseModel
from typing import List, Dict, Optional

class TrainResponse(BaseModel):
    cv_mse: Optional[float]
    n_samples: int
    n_features: int
    n_targets: int
    feature_cols: List[str]
    target_cols: List[str]
    model_type: str

class PredictResponse(BaseModel):
    horizon: List[float]
    feature_row: Dict[str, float]
    meta: Dict[str, str]

class PostFeaturesRequest(BaseModel):
    features: Dict[str, float]
