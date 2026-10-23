FROM python:3.13-slim-bookworm

# Official uv binary, pinned for reproducible dependency installation tooling.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# LightGBM's Linux wheel requires the OpenMP runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

WORKDIR /app
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p data artifacts logs reports \
    && chown -R app:app /app

USER app
EXPOSE 8000 8501 8502
CMD ["python", "-m", "uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
