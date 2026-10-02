# Антифрод-пайплайн (Sparkov, fraudTrain.csv)

Система каждый день выбирает операции для проверки аналитиками так, чтобы спасти больше всего денег при лимите 0,3% операций в сутки. На отложенных двух месяцах (22.04–21.06.2020) экономия — **323 389 у.е., 98,7% от возможного** при таком штате аналитиков.

## Установка (один раз)

Python 3.14, Windows. Версии библиотек зафиксированы, seed = 42.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Положить `fraudTrain.csv` в `data/`.

## Обучение — одна команда

```
.venv\Scripts\python.exe train.py --config configs/final.yaml
```

≈ 1 минута при первом запуске (считаются и кэшируются признаки), потом ≈ 15 секунд. Результат — `artifacts/final/`.

## Скоринг — одна команда

```
.venv\Scripts\python.exe score.py --input <входной_csv> --output <выходной_csv>
```

- Вход — та же структура, что `fraudTrain.csv`, без `is_fraud`; порядок строк любой.
- Выход: `trans_num, fraud_probability, decision, reason_1, reason_2, reason_3` (причины — только у `decision = 1`).
- Модель не переобучается, в сеть не ходит. 550 000 строк — 32 с, 2 ГБ памяти.

## Проверки

```
.venv\Scripts\python.exe -m tests.test_no_future_leak --block a      # тест на утечку (a, b, c, base)
.venv\Scripts\python.exe -m tests.test_leak_canary                   # тест ловит заведомые утечки
.venv\Scripts\python.exe -m tests.test_score_robustness              # score.py: 11 проверок + нагрузка
```

## Воспроизвести исследование

```
.venv\Scripts\python.exe -m src.eda                                  # разведка (только train)
.venv\Scripts\python.exe -m src.evaluate --config configs/baseline_ev.yaml
.venv\Scripts\python.exe -m src.evaluate --config configs/a.yaml --add a_cat_bits a_time_bits ...
.venv\Scripts\python.exe -m experiments.c_experiments
.venv\Scripts\python.exe -m experiments.tournament
.venv\Scripts\python.exe -m experiments.scenarios
.venv\Scripts\python.exe -m src.evaluate --config configs/final.yaml --holdout
.venv\Scripts\python.exe -m experiments.economics_report
.venv\Scripts\python.exe -m experiments.build_feature_map
.venv\Scripts\python.exe -m experiments.examples
```

Каждый прогон дописывается в `reports/experiments.csv`.

## Где что лежит

| Путь | Что |
|---|---|
| `reports/report.md` | отчёт (до 5 страниц) |
| `reports/feature_map.md`, `.csv` | карта признаков: гипотеза, вклад в у.е., тест на утечку, отличие от типичного решения |
| `reports/decision_log.md` | журнал решений |
| `reports/tournament.md` | турнир: наборы признаков × модели |
| `reports/scenarios.md` | кто какой сценарий ловит |
| `reports/economics.md` | экономика на холдауте, стресс-тест, сколько аналитиков |
| `reports/examples.md` | реальные карточки для аналитика |
| `presentation/antifraud.pptx` | презентация с заметками |
| `presentation/cheatsheet.md` | шпаргалка к защите |
| `src/features/profile.py`, `velocity.py`, `context.py` | блоки A, B, C |
| `src/economics.py` | стоимость, лимит, политики выбора |
| `tasks/TASK_*.md`, `CLAUDE.md` | исходные задания |

`data/fraudTest.csv` не использовался.
