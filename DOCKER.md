# Антифрод в Docker

## Быстрый запуск

Нужны Docker Desktop с Linux containers либо Docker Engine и Docker Compose v2+.
Команды выполняются из корня проекта. Python на компьютере устанавливать не нужно.
Для модели и расчёта признаков выделите Docker хотя бы 4 ГБ памяти; обучение и пакетный
скоринг могут требовать больше. Первый запуск скачивает базовый образ и библиотеки.

```bash
docker compose up --build -d --wait
docker compose ps
```

| Компонент | Адрес |
| --- | --- |
| Интерфейс оператора | http://localhost:8501 |
| Панель мониторинга | http://localhost:8502 |
| API / Swagger | http://localhost:8000/docs |
| Готовность модели | http://localhost:8000/health |

В Compose три постоянно работающих контейнера и сервис `tools` для разовых команд.
Оба интерфейса обращаются к API по внутреннему адресу `http://api:8000`.
Они запускаются после успешной проверки `/health`. Streamlit слушает `0.0.0.0`
внутри контейнера; с компьютера порты по умолчанию доступны только через localhost.

```bash
docker compose logs -f
docker compose stop
docker compose start --wait
docker compose down
```

`down` удаляет контейнеры, но сохраняет журнал. `down -v` удаляет и журнал SQLite.
Для пересборки после изменения исходников снова выполните `up --build -d --wait`.

## Данные и модель

Сохраните каталоги `artifacts/` и `data/` рядом с `compose.yaml`: они подключаются
к контейнерам с компьютера. В образ датасеты и модели не копируются.
В Git уже находятся `data/holdout.csv`, модель v2 и история обучения
`artifacts/final/history.parquet`. Поэтому быстрый запуск работает без скачивания Sparkov.

Полная история онлайн-сервиса `data/cache/service_history.parquet` в Git не хранится.
Если её нет, существующий код использует историю обучения. API выдаст предупреждение,
но продолжит работу. Результаты такого демо могут отличаться от цифр в README,
полученных с историей fraudTest до начала holdout.

Для воспроизведения полной истории положите `fraudTest.csv` в `data/`, затем:

```bash
docker compose build
docker compose run --rm tools python -m service.prepare
docker compose up -d --wait
```

Если сервис уже работал, после подготовки перезапустите его и интерфейс, чтобы
модель перечитала историю, а Streamlit сбросил кэш holdout:

```bash
docker compose restart api frontend
docker compose up -d --wait
```

Готовый holdout преподавателя положите в `data/teacher_holdout.csv`:

```bash
docker compose run --rm tools python -m service.prepare --holdout-file data/teacher_holdout.csv
```

Эта команда также требует `data/fraudTest.csv`: скрипт использует его для истории.
Подготовка перезаписывает `data/holdout.csv` и `data/cache/service_history.parquet`.

## Разовые команды

`tools` использует тот же образ и монтирует весь проект с правом записи. Созданные
файлы остаются на компьютере. Сервис не запускается обычной командой `up` и не требует
работающего API для обучения или скоринга. После изменений зависимостей сначала
выполните `docker compose build`.

Подача операций в запущенный API:

```bash
docker compose run --rm tools python replay.py --n 150 --start 0 --pause 0.1
```

Пакетный скоринг и отчёт по рискам:

```bash
docker compose run --rm tools python score.py --input data/holdout.csv --output data/scored.csv --risk-report data/risks.csv
```

Обучение v2 (требуется `data/fraudTrain.csv`; перезаписывает `artifacts/final_v2/`):

```bash
docker compose run --rm tools python train.py --config configs/final_v2.yaml
docker compose restart api
```

Любые исследовательские скрипты доступны аналогично, например:

```bash
docker compose run --rm tools python -m src.eda
docker compose run --rm tools python -m experiments.w2_patterns
docker compose run --rm tools python presentation/build_week3.py
```

Их исходные требования к CSV, предыдущим расчётам и артефактам сохраняются.
В частности, в текущем репозитории нет модели v1 (`artifacts/final/model.pkl`):
для сравнений с v1 сначала нужны её артефакты или обучение `configs/final.yaml`.

## Проверки

```bash
docker compose config --quiet
docker compose run --rm tools python -m pytest tests/test_service.py -q -p no:cacheprovider
```

Тесты создают собственный журнал в `logs/` на компьютере, отдельно от volume
работающего API. Для сверки online/batch сначала подготовьте полную историю:

```bash
docker compose run --rm tools python -m service.check_batch --n 300
```

## Хранение и настройки

- `data/` и `artifacts/` API читает с компьютера без права записи.
- `data/` интерфейс оператора читает для подачи демонстрационных операций.
- Журнал API `/app/logs/journal.sqlite` хранится в именованном volume `journal`
  проекта Compose (по умолчанию `antifraud_journal`).
- История текущей сессии и порог находятся в памяти API. После перезапуска история
  сессии теряется, порог возвращается к 0,5, а счётчики показывают новую сессию.
  Старые записи SQLite остаются. Это существующее поведение приложения.
- API работает с одним worker: дополнительные процессы или реплики получат
  независимые истории карт и пороги.
- Контейнеры работают от обычного пользователя; Linux runtime LightGBM
  `libgomp1` установлен в образ. Python 3.13 соответствует метаданным модели v2.

Для изменения портов скопируйте `.env.example` в `.env` и отредактируйте нужные значения.
Например, `API_PORT=18000`. Внутренний адрес API для контейнеров остаётся `api:8000`.
На Linux, если UID/GID владельца проекта отличаются от 1000, укажите в `.env`
`LOCAL_UID` и `LOCAL_GID` (результаты команд `id -u` и `id -g`), чтобы `tools`
мог записывать файлы без смены владельца. На Windows обычно достаточно значений по умолчанию.

Для доступа по сети задайте `BIND_ADDRESS=0.0.0.0`. У приложения нет аутентификации;
такой режим предназначен для доверенной сети. Ссылку на Swagger в интерфейсе можно
переопределить переменной `ANTIFRAUD_PUBLIC_API` в `compose.yaml` на адрес компьютера,
который открывает браузер.

Если API не готов, проверьте `docker compose logs api`: отсутствующие модели,
неполная загрузка файлов или нехватка памяти видны там. При занятом порте измените `.env`.
