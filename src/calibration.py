"""Калибровка вероятностей (владелец C). Нужна, чтобы p в формуле EV была настоящей вероятностью."""
import numpy as np
import pandas as pd


class Calibrator:
    def __init__(self, method: str = "none"):
        self.method = method

    def fit(self, p, y):
        if self.method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p, y)
        return self

    def transform(self, p):
        if self.method == "isotonic":
            return self.iso.predict(np.asarray(p, dtype="float64"))
        return np.asarray(p, dtype="float64")


def reliability(p, y, bins: int = 10) -> pd.DataFrame:
    """Средняя предсказанная и фактическая доля фрода по корзинам предсказаний (корзины по квантилям положительных p)."""
    p = np.asarray(p, dtype="float64")
    y = np.asarray(y)
    edges = np.unique(np.quantile(p, np.linspace(0.9, 1, bins + 1)))
    edges[0] = 0.0
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    t = pd.DataFrame({"bin": idx, "p": p, "y": y}).groupby("bin").agg(n=("y", "size"), mean_p=("p", "mean"),
                                                                       fraud_rate=("y", "mean"))
    return t.round(4)
