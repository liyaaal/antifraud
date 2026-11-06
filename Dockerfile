# Python and ML library versions match the artifacts in artifacts/final_v2.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# LightGBM needs libgomp at runtime; curl is used by the backend health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

EXPOSE 8000 8501 8502

# docker-compose.yml sets the command for backend, frontend, dashboard, and prepare.
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
