ARG AIRFLOW_VERSION=3.1.0
FROM apache/airflow:${AIRFLOW_VERSION}-python3.13

USER airflow
COPY --chown=airflow:root requirements-model.txt /requirements-model.txt
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.13.txt" \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements-model.txt
