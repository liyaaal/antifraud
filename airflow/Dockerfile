# Образ Airflow для прескоринга (неделя 6).
# Сам Airflow 2.10.5 — на Python 3.12 со своими зависимостями (pandas < 2.2).
# Модель обучена на Python 3.13 + pandas 3 / numpy 2.5 / scikit-learn 1.9 / LightGBM 4.7: эти версии ставятся
# в ОТДЕЛЬНОЕ окружение /opt/airflow/model-venv, и задача score выполняется в нём (@task.external_python).
# Так версии модели совпадают со средой обучения и не ломают сам Airflow.
FROM apache/airflow:2.10.5-python3.12

USER root
# libgomp1 нужен LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

USER airflow
# каталог служебной базы Airflow (том airflow_db) — создаём от имени airflow, чтобы том получил эти права
RUN mkdir -p /opt/airflow/db
COPY requirements-model.txt /tmp/requirements-model.txt
RUN pip install --no-cache-dir "uv>=0.5" \
    && uv python install 3.13 \
    && uv venv --python 3.13 /opt/airflow/model-venv \
    && uv pip install --no-cache --python /opt/airflow/model-venv/bin/python -r /tmp/requirements-model.txt \
    && /opt/airflow/model-venv/bin/python -c "import pandas, sklearn, lightgbm; print('model env ok:', pandas.__version__, sklearn.__version__, lightgbm.__version__)"

ENV MODEL_PYTHON=/opt/airflow/model-venv/bin/python
