# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/python:3.12-alpine3.23 AS build-venv

RUN apk add --no-cache gcc g++ linux-headers

COPY ./src/k8s-scenario-controller/requirements.txt requirements.txt

RUN python -m venv venv && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

FROM docker.io/library/python:3.12-alpine3.23

COPY --from=build-venv /venv/ /venv/

WORKDIR /app

COPY ./src/k8s-scenario-controller/main.py main.py
COPY ./src/k8s-scenario-controller/cluster.py cluster.py
COPY ./src/k8s-scenario-controller/flagclient.py flagclient.py
COPY ./src/k8s-scenario-controller/modules modules

ENV PYTHONUNBUFFERED=1

EXPOSE 8080
ENTRYPOINT ["/venv/bin/python", "main.py"]
