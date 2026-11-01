FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml ./
# No poetry.lock is committed yet — run `poetry lock` locally once and commit it,
# then this will use the locked versions for reproducible builds.
RUN poetry lock --no-update && poetry install --no-root --only main

COPY src ./src
COPY images ./images

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "src/travel_agent/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
