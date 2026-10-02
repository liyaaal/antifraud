"""Сборка признаков из блоков. Один и тот же код в evaluate, train и score."""
import hashlib
import pickle
import time
from pathlib import Path

import pandas as pd

from src.data import CACHE_DIR, ROOT, load_train
from src.features import BLOCK_MODULES, get_block
from src.split import assign, boundaries


def fit_states(train_rows: pd.DataFrame, blocks: list[str]) -> dict:
    return {b: get_block(b).fit(train_rows) for b in blocks}


def compute(df: pd.DataFrame, blocks: list[str], states: dict) -> pd.DataFrame:
    """df отсортирован по (ts, trans_num). Возвращает признаки всех блоков с тем же индексом."""
    parts = []
    for b in blocks:
        t0 = time.time()
        parts.append(get_block(b).transform(df, states[b]))
        print(f"  блок {b}: {time.time() - t0:.1f} c")
    return pd.concat(parts, axis=1)


def _code_hash(block: str) -> str:
    """Кэш признаков сбрасывается, если изменился код блока или очистки данных."""
    files = [ROOT / (BLOCK_MODULES[block].replace(".", "/") + ".py"), ROOT / "src" / "data.py",
             ROOT / "src" / "split.py"]
    h = hashlib.sha1()
    for f in files:
        h.update(Path(f).read_bytes())
    return h.hexdigest()[:12]


def load_dataset(blocks: list[str]):
    """Весь fraudTrain: очищенные строки, часть (train/valid/holdout), признаки блоков, состояния блоков.

    Состояния (популяционные статистики) обучаются только на части train.
    """
    df = load_train()
    b = boundaries(df.ts)
    part = assign(df.ts, b)
    train_rows = df[part == "train"]
    feats, states = [], {}
    for blk in blocks:
        key = _code_hash(blk)
        fpath = CACHE_DIR / f"feat_{blk}_{key}.parquet"
        spath = CACHE_DIR / f"state_{blk}_{key}.pkl"
        if fpath.exists() and spath.exists():
            f = pd.read_parquet(fpath)
            st = pickle.loads(spath.read_bytes())
        else:
            for old in CACHE_DIR.glob(f"feat_{blk}_*.parquet"):
                old.unlink()
            for old in CACHE_DIR.glob(f"state_{blk}_*.pkl"):
                old.unlink()
            t0 = time.time()
            st = get_block(blk).fit(train_rows)
            f = get_block(blk).transform(df, st)
            print(f"  блок {blk}: признаки посчитаны за {time.time() - t0:.1f} c")
            f.to_parquet(fpath)
            spath.write_bytes(pickle.dumps(st))
        if "category" in f.columns:
            f["category"] = pd.Categorical(f["category"], categories=st["categories"])
        feats.append(f)
        states[blk] = st
    X = pd.concat(feats, axis=1)
    return df, part, X, states, b
