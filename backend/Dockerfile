FROM python:3.12-slim-bookworm AS converter-download

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

FROM mambaorg/micromamba:2.0.5-debian12-slim AS pdal-download

USER root

RUN micromamba create --yes --prefix /opt/pdal \
        --channel conda-forge --strict-channel-priority pdal=2.10.2 \
    && LD_LIBRARY_PATH=/opt/pdal/lib /opt/pdal/bin/pdal --version \
    && micromamba clean --all --yes

FROM python:3.12-slim-bookworm AS backend-build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/potree-converter/PotreeConverter_linux_x64:${PATH}" \
    POTREE_CONVERTER_PATH="/opt/potree-converter/PotreeConverter_linux_x64/PotreeConverter" \
    APP_PDAL_PATH="/usr/local/bin/pdal" \
    LD_LIBRARY_PATH="/opt/potree-converter/PotreeConverter_linux_x64"

WORKDIR /app

COPY --from=converter-download /opt/potree-converter/PotreeConverter_linux_x64 /opt/potree-converter/PotreeConverter_linux_x64
COPY --from=pdal-download /opt/pdal /opt/pdal

RUN printf '%s\n' \
        '#!/bin/sh' \
        'export LD_LIBRARY_PATH="/opt/pdal/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"' \
        'export PDAL_DRIVER_PATH="/opt/pdal/lib/pdal/plugins"' \
        'exec /opt/pdal/bin/pdal "$@"' \
        > /usr/local/bin/pdal \
    && chmod 755 /usr/local/bin/pdal

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY tests/test_pdal_crop.py tests/las_fixtures.py /tmp/pdal-tests/
RUN PYTHONPATH=/tmp/pdal-tests python -m unittest discover \
        -s /tmp/pdal-tests -p test_pdal_crop.py -v

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/potree-converter/PotreeConverter_linux_x64:${PATH}" \
    POTREE_CONVERTER_PATH="/opt/potree-converter/PotreeConverter_linux_x64/PotreeConverter" \
    APP_PDAL_PATH="/usr/local/bin/pdal" \
    LD_LIBRARY_PATH="/opt/potree-converter/PotreeConverter_linux_x64"

COPY --from=converter-download /opt/potree-converter/PotreeConverter_linux_x64 /opt/potree-converter/PotreeConverter_linux_x64
COPY --from=pdal-download /opt/pdal /opt/pdal
COPY --from=backend-build /usr/local /usr/local

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --create-home app \
    && mkdir -p /var/lib/point-cloud-explorer \
    && chown -R app:app /app /var/lib/point-cloud-explorer

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
