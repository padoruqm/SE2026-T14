FROM python:3.12-slim AS converter-download

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --silent --show-error \
        https://github.com/potree/PotreeConverter/releases/download/2.1.1/PotreeConverter_2.1.1_x64_linux.zip \
        --output /tmp/potree-converter.zip \
    && echo "6ecf70d2156be36ebeed8b6dbe457e89531e7816aaba814531527288a84294f7  /tmp/potree-converter.zip" \
        | sha256sum --check \
    && unzip -q /tmp/potree-converter.zip -d /opt/potree-converter \
    && chmod 755 /opt/potree-converter/PotreeConverter_linux_x64/PotreeConverter \
    && rm /tmp/potree-converter.zip

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/potree-converter/PotreeConverter_linux_x64:${PATH}" \
    POTREE_CONVERTER_PATH="/opt/potree-converter/PotreeConverter_linux_x64/PotreeConverter" \
    LD_LIBRARY_PATH="/opt/potree-converter/PotreeConverter_linux_x64"

COPY --from=converter-download /opt/potree-converter/PotreeConverter_linux_x64 /opt/potree-converter/PotreeConverter_linux_x64

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
