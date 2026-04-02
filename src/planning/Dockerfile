# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/python:3.12-alpine3.22 AS build-venv

RUN apk update && \
    apk add gcc g++ linux-headers librdkafka-dev

COPY ./src/planning/requirements.txt requirements.txt

RUN python -m venv venv && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

RUN venv/bin/opentelemetry-bootstrap -a install

FROM docker.io/library/python:3.12-alpine3.22

RUN apk add --no-cache librdkafka

COPY --from=build-venv /venv/ /venv/

WORKDIR /app

COPY ./src/planning/demo_pb2.py demo_pb2.py
COPY ./src/planning/logger.py logger.py
COPY ./src/planning/planning_server.py planning_server.py

EXPOSE ${PLANNING_PORT}
ENTRYPOINT [ "/venv/bin/opentelemetry-instrument", "/venv/bin/python", "planning_server.py" ]
