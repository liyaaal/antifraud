"""Группы риска (неделя 2, замечание преподавателя): «высокий» / «средний» / «низкий».

Группа задаётся откалиброванной вероятностью мошенничества p (та же, что в колонке fraud_probability):
  высокий  — p ≥ 0,90  («точно мошенник»: на valid 99,4% таких операций — фрод);
  средний  — 0,10 ≤ p < 0,90 («подозрительно»: на valid фрод у 39%);
  низкий   — p < 0,10  («не мошенник»: на valid фрод у 0,01%).
Пороги выбраны на valid (21.02–21.04.2020) и не подбирались ни на holdout, ни на fraudTest.

Группа — это описание операции для людей. Решение «отправить аналитику» (decision) по-прежнему принимает
денежная политика ev_cap в пределах лимита 0,3% в день: из группы «средний» дорогая операция может уйти
к аналитику раньше дешёвой из группы «высокий».
"""
import numpy as np
import pandas as pd

HIGH = 0.90
LOW = 0.10
LEVELS = ["высокий", "средний", "низкий"]


def risk_level(p) -> np.ndarray:
    p = np.asarray(p, dtype="float64")
    return np.where(p >= HIGH, "высокий", np.where(p >= LOW, "средний", "низкий"))


def _n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def summary_text(out: pd.DataFrame, raw: pd.DataFrame | None = None, ts: pd.Series | None = None) -> str:
    """Сводка для консоли. Если во входе есть is_fraud — добавляется сверка с ответами (только отчёт:
    в скоринге метки не участвуют, score_frame удаляет колонку до расчёта)."""
    lvl = risk_level(out["fraud_probability"])
    dec = out["decision"].to_numpy() == 1
    n = len(out)
    days = ts.dt.normalize().nunique() if ts is not None else None
    lines = ["", "Группы риска (по вероятности мошенничества):"]
    names = {"высокий": "ВЫСОКИЙ  (p ≥ 0,90) — «точно мошенник»",
             "средний": "СРЕДНИЙ  (0,10 ≤ p < 0,90) — «подозрительно»",
             "низкий": "НИЗКИЙ   (p < 0,10) — «не мошенник»"}
    for k in LEVELS:
        m = lvl == k
        lines.append(f"  {names[k]:<48} {_n(m.sum()):>9}   из них отправлено аналитику: {_n((m & dec).sum())}")
    risky = (lvl != "низкий").sum()
    per_day = f" (в среднем {risky / days:.1f} в день, отправлено {dec.sum() / days:.1f} в день)" if days else ""
    lines.append(f"  Рисковых (высокий + средний): {_n(risky)}, отправлено аналитикам: {_n(dec.sum())}{per_day}")
    if raw is not None and "is_fraud" in raw.columns:
        y = out[["trans_num"]].merge(raw[["trans_num", "is_fraud"]].astype({"trans_num": "str"}),
                                     on="trans_num", how="left")["is_fraud"].fillna(0).to_numpy() == 1
        lines += ["", "Сверка с ответами (is_fraud есть во входе; в расчёте вероятностей не использовался):",
                  f"  Мошеннических операций в файле: {_n(y.sum())}"]
        for k in LEVELS:
            m = lvl == k
            lines.append(f"    в группе «{k}»: {_n((m & y).sum()):>7}  ({(m & y).sum() / max(y.sum(), 1):.1%})"
                         f"   — отправлено аналитику {_n((m & y & dec).sum())}")
        lines.append(f"  Отправлено аналитикам: {_n(dec.sum())}, из них мошенников {_n((dec & y).sum())} "
                     f"(точность {(dec & y).sum() / max(dec.sum(), 1):.1%}), честных {_n((dec & ~y).sum())}")
    return "\n".join(lines)
