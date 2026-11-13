"""Чистые функции части 2 (без Airflow): форматирование показателей, промпт, проверка чисел.

Вынесены из DAG, чтобы их можно было проверить тестами (tests/test_report.py) без Airflow и Ollama.
Главное правило недели 6: всё считает код, языковая модель только излагает готовые значения.
"""
import json
import re

# Допущения финансовой модели. Значения по умолчанию; в Airflow их можно переопределить через Variables
# (Admin → Variables: review_cost, commission_rate) — без правки кода. Обоснование — в README.
ASSUMPTIONS = {
    "currency": "USD",          # валюта датасета Sparkov
    "review_cost": 2.0,         # стоимость ручной проверки одной операции, USD
    "commission_rate": 0.015,   # комиссионный доход банка с операции, 1,5%
}

PROMPT = """Ты финансовый аналитик банка. Подготовь резюме результатов
прескоринга для руководителя подразделения финансового мониторинга.

Требования:
- Используй только значения из блока ФАКТЫ без изменений: копируй числа вместе с подписями.
- Не выполняй вычислений, не округляй, не добавляй новые показатели и проценты.
- Не пиши других чисел: ни номеров пунктов, ни количества предложений, ни дат, которых нет в фактах.
- Не используй терминологию машинного обучения.
- Пиши по-русски, обычным текстом без списков и заголовков.
- Объём 5–7 предложений: общий итог, предотвращённые потери,
  понесённые потери, ложные блокировки и их стоимость,
  {compare_line}один вопрос для обсуждения с руководством.

ФАКТЫ:
{facts}"""

REPAIR = """

В прошлом варианте были числа, которых нет в фактах: {extra}. Напиши резюме заново.
Каждое число переписывай из блока ФАКТЫ символ в символ, других чисел не используй."""


def fmt_int(x) -> str:
    """142380 -> «142 380» (обычный пробел как разделитель разрядов)."""
    return f"{int(round(float(x))):,}".replace(",", " ")


def fmt_money(x, currency="USD") -> str:
    """Суммы — в целых USD; маленькие (меньше 100) — с центами, чтобы не превращаться в «0 USD»."""
    x = float(x)
    if abs(x) < 100:
        return f"{x:.2f}".replace(".", ",") + f" {currency}"
    return f"{fmt_int(x)} {currency}"


def fmt_pct(x) -> str:
    return f"{float(x):.1f}".replace(".", ",") + "%"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def ops(n) -> str:
    return f"{fmt_int(n)} {plural(int(n), 'операция', 'операции', 'операций')}"


def compute_finance(agg: dict, a: dict) -> dict:
    """agg — результат SQL (tp, tp_sum, fn, ...). Возвращает все финансовые показатели в числах."""
    flagged = int(agg["flagged"])
    review_cost_total = flagged * float(a["review_cost"])
    lost_commission = float(agg["fp_sum"]) * float(a["commission_rate"])
    net_effect = float(agg["tp_sum"]) - review_cost_total - lost_commission
    coverage = 100.0 * float(agg["tp_sum"]) / float(agg["fraud_sum"]) if float(agg["fraud_sum"]) else 0.0
    return {"review_cost_total": round(review_cost_total, 2), "lost_commission": round(lost_commission, 2),
            "net_effect": round(net_effect, 2), "coverage_pct": round(coverage, 2)}


def build_facts(agg: dict, fin: dict, a: dict, compare: dict | None = None) -> dict:
    """Готовые строки в том виде, в каком они должны попасть в отчёт: модель только переписывает их."""
    cur = a["currency"]
    facts = {
        "период": f"{agg['period_from']:%d.%m.%Y} – {agg['period_to']:%d.%m.%Y}",
        "операций": fmt_int(agg["ops"]),
        "срабатываний": fmt_int(agg["flagged"]),
        "предотвращённые_потери": f"{ops(agg['tp'])} на сумму {fmt_money(agg['tp_sum'], cur)}",
        "понесённые_потери": f"{ops(agg['fn'])} на сумму {fmt_money(agg['fn_sum'], cur)}",
        "покрытие_мошенничества": fmt_pct(fin["coverage_pct"]),
        "ложные_блокировки": f"{ops(agg['fp'])} на сумму {fmt_money(agg['fp_sum'], cur)}",
        "операционные_затраты": fmt_money(fin["review_cost_total"], cur),
        "упущенный_доход": fmt_money(fin["lost_commission"], cur),
        "чистый_эффект": fmt_money(fin["net_effect"], cur),
    }
    if compare:
        facts["сравнение_с_прежней_версией"] = (
            f"прежняя версия предотвратила бы потери на сумму {fmt_money(compare['tp_sum'], cur)}, "
            f"чистый эффект {fmt_money(compare['net_effect'], cur)}")
    return facts


def make_prompt(facts: dict, extra: set | None = None) -> str:
    compare_line = ("одно предложение о сравнении с прежней версией,\n  "
                    if "сравнение_с_прежней_версией" in facts else "")
    p = PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=2), compare_line=compare_line)
    if extra:
        p += REPAIR.format(extra=", ".join(sorted(extra)))
    return p


_NUM = re.compile(r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def numbers(s: str) -> set[str]:
    """Все числа в тексте. «142 380» — одно число с разделителем разрядов; «82,8» и «82.8» — одно и то же."""
    return {re.sub(r"\s", "", n).replace(",", ".") for n in _NUM.findall(s)}


def check_report(report: str, facts: dict) -> tuple[bool, set[str]]:
    allowed = set().union(*(numbers(str(v)) for v in facts.values()))
    extra = numbers(report) - allowed
    return len(extra) == 0, extra
