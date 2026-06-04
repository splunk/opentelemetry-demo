# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/python:3.12-alpine3.23 AS build-venv

COPY ./src/report-generator/requirements.txt requirements.txt

RUN python -m venv venv && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

RUN venv/bin/opentelemetry-bootstrap -a install

FROM docker.io/library/python:3.12-alpine3.23

COPY --from=build-venv /venv/ /venv/

WORKDIR /app

COPY ./src/report-generator/report_server.py report_server.py

EXPOSE ${REPORT_PORT}
ENTRYPOINT [ "/venv/bin/opentelemetry-instrument", "/venv/bin/python", "report_server.py" ]
