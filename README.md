# Антифрод-пайплайн (Sparkov, fraudTrain.csv)

Система каждый день выбирает операции для проверки аналитиками так, чтобы спасти больше всего денег при лимите 0,3% операций в сутки. На отложенных двух месяцах (22.04–21.06.2020) экономия — **323 389 у.е., 98,7% от возможного** при таком штате аналитиков.


## Неделя 3 — антифрод в реальном времени (сдача 17.10.2026)

Модель v2 стала сервисом: операция приходит по одной, решение — сразу. Кратко, что сделано и как запустить: `ОБНОВА_неделя3_читать_первым.md`.

```
Интерфейс оператора (Streamlit, :8501) ──┐                       ┌─ модель v2 + код признаков score.py (один раз при старте)
                                          ├── HTTP/JSON ── FastAPI (:8000) ─┼─ история карт в памяти {cc_num: операции}
Панель мониторинга  (Streamlit, :8502) ──┘                       └─ журнал SQLite logs/journal.sqlite
```

Интерфейс и панель не загружают модель и не читают журнал — только запросы к сервису.

### Запуск (Windows, из папки проекта; три окна терминала)

```
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m service.prepare          # один раз: data/holdout.csv и стартовая история карт

# окно 1 — сервис, документация на http://localhost:8000/docs
..\.venv\Scripts\python.exe -m uvicorn service.main:app --port 8000
# окно 2 — интерфейс оператора, http://localhost:8501
..\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.port 8501
# окно 3 — панель мониторинга, http://localhost:8502
..\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.port 8502
# по желанию, окно 4 — серия операций из терминала
..\.venv\Scripts\python.exe replay.py --n 150 --start 0
```

На Linux/macOS то же без `..\.venv\Scripts\`: `uvicorn service.main:app --port 8000`, `streamlit run frontend/app.py --server.port 8501`, `streamlit run dashboard/app.py --server.port 8502`. Сервис стартует 10–20 с: загружает модель и историю карт (1,7 млн операций).

### Маршруты API

| Маршрут | Что делает | Ответ |
|---|---|---|
| `POST /predict` | одна операция — строка датасета Sparkov без `is_fraud` | `transaction_id`, `fraud_score`, `is_fraud_pred`, `threshold` + `risk_level`, `expected_value`, `reasons`, `card_history`, `latency_ms` |
| `POST /label` | фактическая метка: `transaction_id`, `is_fraud` | подтверждение; 404, если такой операции не было |
| `GET /metrics` | данные для панели (`?bucket=50` — размер точки графика) | сводка, ряды по запросам и по минутам, последние срабатывания и ошибки, тревоги |
| `GET /health` | сервис жив, модель загружена | `{"status": "ok", ...}` |
| `PUT /threshold` | смена порога без перезапуска (дополнительно) | старый и новый порог |
| `POST /session/new` | начать счёт показателей заново (дополнительно) | номер сессии |

Некорректный вход (нет поля, текст вместо числа, неизвестная категория, отрицательная сумма) FastAPI отклоняет с кодом **422**; такой запрос пишется в журнал со статусом «ошибка» и снижает success rate. Если упадёт модель — код **500**, тоже в журнал.

### Принятые решения

- **Тот же код, что `score.py`.** Признаки модели v2 считаются по истории одной карты и по таблицам, выученным на train. Сервис берёт прошлые операции карты, дописывает новую и вызывает `src.pipeline.compute`. Сверка: `python -m service.check_batch --n 300` — расхождение с пакетным `score_frame` **0** на 300 операциях из 300.
- **История карт — словарь в памяти** `{cc_num: прошлые операции}`. Стартовая история — fraudTrain + fraudTest до начала holdout, без меток (`data/cache/service_history.parquet`). Каждая операция, пришедшая в сервис, дописывается к своей карте. После перезапуска операции сессии теряются, стартовая история остаётся.
- **Порог 0,5** по откалиброванной вероятности: «мошенничество вероятнее, чем нет». На valid: точность 98,3%, чувствительность 94,1%. Меняется через `PUT /threshold`. Группа риска недели 2 (≥ 0,9 / 0,1–0,9 / < 0,1) и EV возвращаются для оператора. Лимит 0,3% проверок в сутки из недель 1–2 — это суточная очередь аналитиков, а не решение по одной операции; в сервисе его нет.
- **Журнал — SQLite** `logs/journal.sqlite`: время, операция, оценка, решение, порог, статус, код ошибки, время ответа, метка. Переживает перезапуск; панель считает показатели по текущей сессии.
- **Стек — Streamlit** для интерфейса и панели: команда пишет на Python, Streamlit не требует JS и CORS, автообновление панели — `@st.fragment(run_every="5s")`. HTML/CSS дал бы больше свободы в оформлении, но потребовал бы JavaScript (`fetch`, `setInterval`); `CORSMiddleware` в сервисе всё равно включён.

### Holdout

Отложенного периода, не использованного ни в обучении, ни в сравнении версий, не осталось: fraudTrain ушёл на train/valid/holdout, fraudTest — на сравнение v1/v2 недели 2. По ТЗ такой период выдаёт преподаватель — тогда `python -m service.prepare --holdout-file <файл>`. До этого `data/holdout.csv` — 9 суток fraudTest: **02.12.2020 22:00 – 11.12.2020 22:00, 38 981 операция, 131 мошенническая**. На них модель не обучалась и ничего не настраивалось. Начало 22:00 выбрано, чтобы в первой серии из 200 операций была вечерняя волна мошенничества (13 операций): при доле фрода 0,3% в случайных 200 операциях в среднем меньше одной.

### Определения на панели

| Показатель | Как считается | Что показывает |
|---|---|---|
| Success rate | запросы к `/predict` без ошибки / все запросы к `/predict` | работает ли сервис (не качество модели) |
| Fraud rate, модель | операции с `is_fraud_pred = 1` / успешно обработанные | сколько модель останавливает; известен сразу |
| Fraud rate, факт | `is_fraud = 1` / операции, для которых пришла метка | сколько фрода было на самом деле; известен позже |

Два fraud rate различаются из-за ошибок модели (ложные тревоги FP поднимают модельный, пропуски FN — фактический) и потому, что метки приходят не для всех операций и с задержкой. Дополнительно на панели: точность и чувствительность по размеченным, суммы остановленного и пропущенного фрода, время ответа (медиана и p95), тревога при success rate < 95%.

### Проверки

```
..\.venv\Scripts\python.exe -m pytest tests/test_service.py -q     # 5 тестов: health, predict+label, 422 в журнале, 404, порог
..\.venv\Scripts\python.exe -m service.check_batch --n 300         # сервис = score.py
```

Прогон 150 операций holdout с начала (`replay.py --n 150`): 11 мошеннических, все 11 помечены, ложных тревог 0; время ответа ≈ 0,2 с (медиана), ≈ 0,3 с (p95).

### Известные ограничения

- Одна операция считается ≈ 0,2 с: признаки пересчитываются по всей истории карты (до ~2 000 операций). Для потока в тысячи операций в секунду признаки нужно хранить инкрементально.
- История сессии живёт в памяти одного процесса: при перезапуске теряется, при нескольких копиях сервиса — не общая.
- Операции нужно подавать по времени: операция «из прошлого» видит только более раннюю историю карты, но уже поданные более поздние операции не пересчитываются.
- Лимит 0,3% проверок в сутки в сервисе не применяется: решение по порогу.


## Неделя 2 — вторая итерация (сдача 10.10.2026)

Кратко, что изменено и где что лежит: `ОБНОВА_неделя2_читать_первым.md`.

Сейчас в репозитории две версии. Обе запускаются одним и тем же `score.py`: интерфейс и колонки выхода прежние.

| Версия | Что это | Артефакты | Конфиг |
|---|---|---|---|
| **v2 (текущая)** | v1 + блок E «эпизод захвата карты» (3 признака) | `artifacts/final_v2/` | `configs/final_v2.yaml` |
| v1 (неделя 1, защищена 03.10) | как сдавали | `artifacts/final/` | `configs/final.yaml` |

```
# v2 — по умолчанию
.venv\Scripts\python.exe score.py --input <входной_csv> --output <выходной_csv>

# v1 — те же файлы кода, артефакты недели 1 (выход побайтно совпадает с кодом по тегу v1-week1)
.venv\Scripts\python.exe score.py --input <входной_csv> --output <выходной_csv> --artifacts artifacts/final

# v1 — ровно код недели 1, в отдельной папке
git worktree add ..\antifraud_v1 v1-week1
cd ..\antifraud_v1
..\antifraud\.venv\Scripts\python.exe score.py --input <входной_csv> --output <выходной_csv>
```

При каждом запуске `score.py` печатает сводку **по группам риска** (замечание преподавателя): высокий (p ≥ 0,90, «точно мошенник»), средний (0,10–0,90), низкий (p < 0,10) — сколько операций в группе и сколько отправлено аналитикам. Если во входном файле есть `is_fraud`, печатается сверка: «мошеннических N, из них в группе высокий / средний / низкий». Метки при этом в расчёте не участвуют. Флаг `--risk-report <файл>` пишет группу каждой операции в отдельный файл. Колонки основного выхода прежние.

**Лимит 0,3% — это ≈ 7 проверок в день, а не 7 аналитиков.** Формула выбора: `EV = p · (сумма + 5) − 3 − (1 − p) · 25`. «Потолок» 327 812 у.е. на holdout — столько спас бы оракул, знающий ответы, при том же лимите. Расчёт по слагаемым — в `reports/week2/1_remarks.md`.

Переобучить v2: `.venv\Scripts\python.exe train.py --config configs/final_v2.yaml` (≈ 2 мин).

**Документы недели 2** — `reports/week2/`:

| Файл | Раздел ТЗ |
|---|---|
| `1_remarks.md` | 3 — ответы на замечания преподавателя (группы риска, PR, баланс, лимит, 328, LogReg) |
| `2_pattern_map.md` | 4, шаг 1 — карта паттернов |
| `3_error_analysis.md` | 4, шаг 2 — анализ ошибок (**основной документ**) |
| `4_solution_evaluation.md` | 5 — оценка решения для инженера сопровождения |
| `5_sens_spec.md` | 6 — чувствительность и специфичность |
| `6_comparison.md` | 7 — v1 против v2 на fraudTest |
| `tables/` | все таблицы, графики и построчные просмотры, которые делают скрипты |
| `presentation/week2.pptx` | презентация на 5–10 минут |

**Главное:**

- Мошенничество в данных — один устойчивый сценарий: двухсуточный захват карты.
- Модель узнаёт его почти всегда. 98% упущенных денег — это узнанные операции, которые не поместились в лимит 0,3%.
- На приёмке (fraudTest, 194 дня) v2 даёт 833 947 у.е. против 830 484 у v1: +3 462, 90% интервал [+55; +7 287].
- Расхождение между своей оценкой и приёмкой сократилось с −1,1 до 0,0 п.п. доли от лучшего возможного.

**Воспроизвести неделю 2** (нужны `data/fraudTrain.csv` и `data/fraudTest.csv`):

```
.venv\Scripts\python.exe -m experiments.w2_patterns                 # эпизоды и карта паттернов (fraudTrain)
.venv\Scripts\python.exe -m tests.test_no_future_leak --block e     # тест на утечку нового блока
.venv\Scripts\python.exe -m src.evaluate --config configs/final_v2.yaml --add e_h_since_big e_big_48h e_usual_ratio e_usual_48h e_night_48h e_amt_48h_log e_cats_48h e_big_rate_hist
.venv\Scripts\python.exe -m src.evaluate --config configs/final_v2.yaml
.venv\Scripts\python.exe -m src.evaluate --config configs/final_v2.yaml --holdout
.venv\Scripts\python.exe train.py --config configs/final_v2.yaml
.venv\Scripts\python.exe -m experiments.w2_errors                   # ошибки v1 + контроль регрессий v2
.venv\Scripts\python.exe -m experiments.w2_raw_scores --config configs/final.yaml
.venv\Scripts\python.exe -m experiments.w2_raw_scores --config configs/final_v2.yaml
.venv\Scripts\python.exe -m experiments.w2_calibration
.venv\Scripts\python.exe -m experiments.w2_sens_spec --version final
.venv\Scripts\python.exe -m experiments.w2_sens_spec --version final_v2
.venv\Scripts\python.exe -m experiments.w2_block
# приёмка — один раз, после заморозки v2:
.venv\Scripts\python.exe score.py --input data/fraudTest.csv --output data/cache/scored_v1_test.csv --artifacts artifacts/final
.venv\Scripts\python.exe score.py --input data/fraudTest.csv --output data/cache/scored_v2_test.csv
.venv\Scripts\python.exe -m experiments.w2_compare
.venv\Scripts\python.exe -m experiments.w2_patterns --test
.venv\Scripts\python.exe -m experiments.w2_sens_spec --version final --scored data/cache/scored_v1_test.csv --tag test
.venv\Scripts\python.exe -m experiments.w2_sens_spec --version final_v2 --scored data/cache/scored_v2_test.csv --tag test
.venv\Scripts\python.exe -m experiments.w2_block --scored-v1 data/cache/scored_v1_test.csv --scored-v2 data/cache/scored_v2_test.csv --tag test
.venv\Scripts\python.exe -m experiments.w2_stress --artifacts artifacts/final_v2 --tag v2
.venv\Scripts\python.exe -m experiments.w2_remarks                  # расчёты к замечаниям: группы, PR-кривая, баланс, 328
.venv\Scripts\python.exe -m tests.test_score_robustness --skip-load --artifacts artifacts/final_v2
```

Ниже — описание недели 1. Оно не менялось, кроме двух строк про fraudTest в конце.

## Установка (один раз)

Python 3.14, Windows. Версии библиотек зафиксированы, seed = 42.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Положить `fraudTrain.csv` (и для недели 2 — `fraudTest.csv`) в `data/`.

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

`data/fraudTest.csv` на неделе 1 не использовался. На неделе 2 он открыт один раз, после заморозки v2, для приёмки обеих версий (`reports/week2/6_comparison.md`).
