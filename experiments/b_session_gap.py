"""B5: чувствительность к порогу сессии G (1 ч / 3 ч / 6 ч). Признаки считаются заново, без кэша."""
import pandas as pd

from src.evaluate import feature_list, load_config, run
from src.features import velocity
from src.pipeline import load_dataset
from src.split import assign

cfg = load_config("configs/b.yaml")
df, part, X, states, b = load_dataset(["base", "b"])
feats = feature_list(cfg)
for g in [1.0, 6.0, 3.0]:
    velocity.SESSION_GAP_H = g
    fb = velocity.transform(df, states["b"])
    X2 = X.copy()
    X2[velocity.FEATURES] = fb[velocity.FEATURES]
    cfg["name"] = f"b_gap{g:g}h"
    run(cfg, feats, df, part, X2, "valid", added=f"G={g:g}ч", note="чувствительность к порогу сессии")
