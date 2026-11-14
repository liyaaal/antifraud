"""Тесты части 2 недели 6 (без Airflow и Ollama): форматирование фактов и проверка чисел в отчёте."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "airflow" / "dags"))
import report_lib as rl  # noqa: E402

AGG = {"ops": 38981, "flagged": 114, "tp": 113, "tp_sum": 71541.41, "fn": 18, "fn_sum": 3021.96,
       "fp": 1, "fp_sum": 23.49, "fraud_sum": 74563.37,
       "period_from": datetime(2020, 12, 2, 22, 0, 5), "period_to": datetime(2020, 12, 11, 21, 59, 40)}


def facts():
    fin = rl.compute_finance(AGG, rl.ASSUMPTIONS)
    return fin, rl.build_facts(AGG, fin, rl.ASSUMPTIONS)


def test_finance_formulas():
    fin, _ = facts()
    assert fin["review_cost_total"] == 114 * 2.0                      # срабатывания × стоимость проверки
    assert fin["lost_commission"] == round(23.49 * 0.015, 2)          # ложные блокировки × комиссия
    assert fin["net_effect"] == round(71541.41 - 228 - 23.49 * 0.015, 2)
    assert abs(fin["coverage_pct"] - 95.95) < 0.01


def test_facts_format():
    _, f = facts()
    assert f["операций"] == "38 981"
    assert f["предотвращённые_потери"] == "113 операций на сумму 71 541 USD"
    assert f["ложные_блокировки"] == "1 операция на сумму 23,49 USD"
    assert f["покрытие_мошенничества"] == "96,0%"


def test_check_passes_when_numbers_copied():
    _, f = facts()
    text = (f"За период {f['период']} обработано {f['операций']} операций. Предотвращено: "
            f"{f['предотвращённые_потери']}, покрытие {f['покрытие_мошенничества']}. Чистый эффект {f['чистый_эффект']}.")
    ok, extra = rl.check_report(text, f)
    assert ok and not extra


def test_check_catches_invented_and_recomputed_numbers():
    _, f = facts()
    ok, extra = rl.check_report("Чистый эффект 71 313 USD, это на 12% больше, а потери 3 000 USD.", f)
    assert not ok and extra == {"12", "3000"}


def test_thousands_separator_variants():
    assert rl.numbers("142 380 и 142 380 и 82,8%") == {"142380", "82.8"}


def test_plural():
    assert [rl.ops(n) for n in (1, 2, 5, 11, 21, 114)] == [
        "1 операция", "2 операции", "5 операций", "11 операций", "21 операция", "114 операций"]
