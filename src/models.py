"""Модели с общим интерфейсом: fit / predict_proba / contributions (CLAUDE.md, раздел 8).

Гиперпараметры фиксированы и не тюнятся — решение команды.
"""
import numpy as np
import pandas as pd

SEED = 42


class LogRegModel:
    name = "logreg"

    def __init__(self, params=None):
        self.params = {"C": 1.0, "max_iter": 2000, **(params or {})}

    def _design(self, X: pd.DataFrame, fit=False) -> pd.DataFrame:
        X = X.copy()
        if fit:
            self.cat_cols = [c for c in X.columns if isinstance(X[c].dtype, pd.CategoricalDtype)]
            self.num_cols = [c for c in X.columns if c not in self.cat_cols]
            self.medians = X[self.num_cols].median()
            self.na_cols = [c for c in self.num_cols if X[c].isna().any()]
            self.cats = {c: list(X[c].cat.categories) for c in self.cat_cols}
        out = {}
        for c in self.num_cols:
            out[c] = X[c].astype("float64").fillna(self.medians[c]).to_numpy()
        for c in self.na_cols:
            out[f"{c}__isna"] = X[c].isna().astype("float64").to_numpy()
        for c in self.cat_cols:
            vals = X[c].astype("object").to_numpy()
            for v in self.cats[c][1:]:  # первая категория — опорная
                out[f"{c}__{v}"] = (vals == v).astype("float64")
        return pd.DataFrame(out, index=X.index)

    def fit(self, X, y, X_valid=None, y_valid=None, sample_weight=None, monotone=None):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        D = self._design(X, fit=True)
        self.columns = list(D.columns)
        self.scaler = StandardScaler().fit(D.to_numpy())
        self.clf = LogisticRegression(**self.params, random_state=SEED)
        self.clf.fit(self.scaler.transform(D.to_numpy()), y, sample_weight=sample_weight)
        return self

    def predict_proba(self, X) -> np.ndarray:
        D = self._design(X)[self.columns]
        return self.clf.predict_proba(self.scaler.transform(D.to_numpy()))[:, 1]

    def contributions(self, X) -> pd.DataFrame:
        """Вклад признака = coef · x_scaled; дамми и флаги пропусков сворачиваются к исходному признаку."""
        D = self._design(X)[self.columns]
        Z = self.scaler.transform(D.to_numpy()) * self.clf.coef_[0]
        C = pd.DataFrame(Z, index=X.index, columns=self.columns)
        owner = {c: c.split("__")[0] for c in self.columns}
        return C.T.groupby(owner).sum().T

    def importance(self) -> pd.Series:
        return pd.Series(self.clf.coef_[0], index=self.columns)


class LGBMModel:
    name = "lgbm"

    def __init__(self, params=None):
        self.params = {
            "n_estimators": 2000, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 100,
            "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8,
            "random_state": SEED, "n_jobs": 16, "verbose": -1, **(params or {}),
        }

    def fit(self, X, y, X_valid=None, y_valid=None, sample_weight=None, monotone=None):
        import lightgbm as lgb

        params = dict(self.params)
        if monotone:
            params["monotone_constraints"] = [int(monotone.get(c, 0)) for c in X.columns]
            params["monotone_constraints_method"] = "advanced"
        self.columns = list(X.columns)
        self.clf = lgb.LGBMClassifier(**params)
        callbacks, eval_kw = [], {}
        if X_valid is not None:
            eval_kw = {"eval_X": (X_valid[self.columns],), "eval_y": (y_valid,)}
            callbacks = [lgb.early_stopping(100, verbose=False)]
        self.clf.fit(X[self.columns], y, sample_weight=sample_weight, **eval_kw,
                     eval_metric="average_precision", callbacks=callbacks)
        self.best_iteration = self.clf.best_iteration_ or params["n_estimators"]
        return self

    def predict_proba(self, X) -> np.ndarray:
        return self.clf.predict_proba(X[self.columns], num_iteration=self.best_iteration)[:, 1]

    def contributions(self, X) -> pd.DataFrame:
        C = self.clf.predict(X[self.columns], pred_contrib=True, num_iteration=self.best_iteration)
        return pd.DataFrame(C[:, :-1], index=X.index, columns=self.columns)

    def importance(self) -> pd.Series:
        return pd.Series(self.clf.booster_.feature_importance("gain"), index=self.columns)


class IForestModel:
    """Без учителя: скор аномальности, приведённый к [0, 1] по рангу на train. Это не вероятность."""
    name = "iforest"

    def __init__(self, params=None):
        self.params = {"n_estimators": 300, "random_state": SEED, "n_jobs": 16, **(params or {})}

    def fit(self, X, y=None, X_valid=None, y_valid=None, sample_weight=None, monotone=None):
        from sklearn.ensemble import IsolationForest

        self.inner = LogRegModel()
        D = self.inner._design(X, fit=True)
        self.columns = list(D.columns)
        self.clf = IsolationForest(**self.params).fit(D.to_numpy())
        self.ref = np.sort(-self.clf.score_samples(D.to_numpy()))
        return self

    def predict_proba(self, X) -> np.ndarray:
        D = self.inner._design(X)[self.columns]
        s = -self.clf.score_samples(D.to_numpy())
        return np.searchsorted(self.ref, s) / len(self.ref)

    def contributions(self, X) -> pd.DataFrame:
        return pd.DataFrame(index=X.index)


MODELS = {"logreg": LogRegModel, "lgbm": LGBMModel, "iforest": IForestModel}


def make_model(name: str, params=None):
    return MODELS[name](params)
