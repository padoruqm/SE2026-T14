FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && mkdir -p /var/lib/point-cloud-explorer \
    && chown -R app:app /app /var/lib/point-cloud-explorer

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
