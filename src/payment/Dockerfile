# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Build argument to determine version (A or B)
ARG VERSION=A

# -----------------------------------------------------------------------------
# Builder stage
# -----------------------------------------------------------------------------

FROM docker.io/library/node:22-slim AS builder

# Pass VERSION arg to builder
ARG VERSION
ENV PAYMENT_VERSION=v${VERSION}

WORKDIR /app

COPY ./src/payment/package.json package.json
COPY ./src/payment/package-lock.json package-lock.json

RUN npm ci --omit=dev

# Create version metadata file (helpful for debugging)
RUN echo "{ \
  \"version\": \"${PAYMENT_VERSION}\", \
  \"buildTime\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \
  \"nodeVersion\": \"$(node --version)\", \
  \"imageVariant\": \"${VERSION}\" \
}" > /app/version.json && cat /app/version.json

# -----------------------------------------------------------------------------
# Production stage
# -----------------------------------------------------------------------------

FROM gcr.io/distroless/nodejs22-debian12:nonroot

# Pass VERSION arg to production stage
ARG VERSION
ENV PAYMENT_VERSION=v${VERSION}
ENV NODE_ENV=production
ENV PAYMENT_PORT=8080

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /app/node_modules/ node_modules/

# Copy version metadata
COPY --from=builder /app/version.json version.json

# Copy protocol buffer definition
COPY ./pb/demo.proto demo.proto

# Copy application code
COPY ./src/payment/charge.js charge.js
COPY ./src/payment/index.js index.js
COPY ./src/payment/logger.js logger.js
COPY ./src/payment/opentelemetry.js opentelemetry.js

# Copy version-specific configuration
COPY ./src/payment/config/ config/

# Add image labels for better tracking
LABEL org.opencontainers.image.title="Payment Service v${VERSION}"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL app.payment.variant="${VERSION}"
LABEL app.service.name="payment-v${VERSION}"

EXPOSE ${PAYMENT_PORT}

CMD ["--require=./opentelemetry.js", "index.js"]
