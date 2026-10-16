"""Онлайн-скоринг одной операции тем же кодом, что и score.py (неделя 3).

Признаки модели v2 считаются по истории ОДНОЙ карты (блоки a, b, e) и по популяционным
таблицам, выученным на train (states.pkl). Поэтому для новой операции достаточно взять
прошлые операции этой карты, дописать к ним новую строку и прогнать обычный src.pipeline.compute.
Результат совпадает с пакетным score.py (проверка: python -m service.check_batch).

История карт хранится в памяти: {cc_num: DataFrame прошлых операций}. Стартовая история —
data/cache/service_history.parquet (готовит python -m service.prepare). Операции, пришедшие
в сервис, дописываются в историю своей карты. После перезапуска сервиса они теряются — это
допустимо по ТЗ недели 3.
"""
import contextlib
import io
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from score import load_artifacts
from src.data import ROOT, clean
from src.economics import expected_value
from src.pipeline import compute
from src.reasons import top_reasons
from src.risk import risk_level

ARTIFACTS = ROOT / "artifacts" / "final_v2"
SERVICE_HISTORY = ROOT / "data" / "cache" / "service_history.parquet"


class OnlineScorer:
    def __init__(self, artifacts: Path = ARTIFACTS, history_path: Path = SERVICE_HISTORY):
        t0 = time.time()
        self.art = load_artifacts(Path(artifacts))
        self.cfg = self.art["meta"]["config"]
        self.features = self.art["meta"]["features"]
        self.version = self.cfg.get("name", "final_v2")
        hp = Path(history_path)
        if not hp.exists():   # подготовка не запускалась — берём историю обучения, как score.py
            hp = Path(self.art["history"])
        self.history_source = str(hp)
        hist = pd.read_parquet(hp)
        hist = hist.sort_values(["cc_num", "ts", "trans_num"], kind="mergesort")
        self.hist = {cc: g.reset_index(drop=True) for cc, g in hist.groupby("cc_num", sort=False)}
        self.history_rows = len(hist)
        self.history_end = str(hist["ts"].max())
        self.session_rows = 0
        self.lock = threading.Lock()
        self.load_seconds = round(time.time() - t0, 1)

    def score(self, raw: dict) -> dict:
        """raw — строка датасета Sparkov (без is_fraud). Возвращает вероятность, EV, группу риска и причины."""
        frame = pd.DataFrame([raw])
        new = clean(frame)
        if new["ts"].isna().any():
            raise ValueError("не удалось разобрать trans_date_trans_time")
        if new["age"].isna().any():
            raise ValueError("не удалось разобрать dob")
        row = new.iloc[0]
        cc = int(row["cc_num"])
        with self.lock:
            past = self.hist.get(cc)
            if past is not None:
                past = past[(past["ts"] <= row["ts"]) & (past["trans_num"] != row["trans_num"])]
                df = pd.concat([past.assign(_input=False), new.assign(_input=True)], ignore_index=True)
            else:
                df = new.assign(_input=True)
            df = df.sort_values(["ts", "trans_num"], kind="mergesort").reset_index(drop=True)
            with contextlib.redirect_stdout(io.StringIO()):     # compute печатает время блоков
                X = compute(df, self.cfg["blocks"], self.art["states"])
            i = int(np.flatnonzero(df["_input"].to_numpy())[0])
            Xi = X.loc[[i], self.features]
            p = float(self.art["cal"].transform(self.art["model"].predict_proba(Xi))[0])

            contrib = self.art["model"].contributions(Xi)
            rows = pd.concat([df.loc[[i], ["amt"]], X.loc[[i]].drop(columns=["amt", "category"], errors="ignore")],
                             axis=1)
            rows["category"] = str(row["category"])
            rows["hour"] = row["ts"].hour
            rows["minute"] = row["ts"].minute
            reasons = [r for r in top_reasons(contrib, rows).iloc[0].tolist() if r]

            # операция становится историей своей карты
            keep = self.hist.get(cc)
            add = new.drop(columns=[c for c in ["is_fraud"] if c in new.columns])
            if keep is None:
                self.hist[cc] = add.reset_index(drop=True)
            else:
                keep = keep[keep["trans_num"] != row["trans_num"]]
                self.hist[cc] = pd.concat([keep, add], ignore_index=True).sort_values(
                    ["ts", "trans_num"], kind="mergesort").reset_index(drop=True)
            self.session_rows += 1
        return {
            "p": round(p, 6),
            "ev": round(float(expected_value(p, float(row["amt"]))), 2),
            "risk_level": str(risk_level([p])[0]),
            "reasons": reasons,
            "card_history": int(len(df) - 1),
            "cc_num": cc,
            "amt": float(row["amt"]),
            "category": str(row["category"]),
            "op_time": str(row["ts"]),
        }
