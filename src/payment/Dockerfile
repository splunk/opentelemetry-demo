# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# -----------------------------------------------------------------------------
# Builder stage
# -----------------------------------------------------------------------------

FROM docker.io/library/node:22-slim AS builder

WORKDIR /app

COPY ./src/payment/package.json package.json
COPY ./src/payment/package-lock.json package-lock.json

RUN npm ci --omit=dev

# -----------------------------------------------------------------------------
# Production stage
# -----------------------------------------------------------------------------

FROM gcr.io/distroless/nodejs22-debian12:nonroot

ENV NODE_ENV=production
ENV PAYMENT_PORT=8080

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /app/node_modules/ node_modules/

# Copy protocol buffer definition
COPY ./pb/demo.proto demo.proto

# Copy application code
COPY ./src/payment/charge.js charge.js
COPY ./src/payment/index.js index.js
COPY ./src/payment/logger.js logger.js
COPY ./src/payment/opentelemetry.js opentelemetry.js

# Copy version configurations (A/B selected at runtime via PAYMENT_VERSION env var)
COPY ./src/payment/config/ config/

EXPOSE ${PAYMENT_PORT}

CMD ["--require=./opentelemetry.js", "index.js"]
