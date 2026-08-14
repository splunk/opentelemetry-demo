# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# --- build: compile the single source file against the JDBC driver ---
FROM --platform=${BUILDPLATFORM} eclipse-temurin:21-jdk AS builder
WORKDIR /build

# Postgres JDBC driver (baked into the image so runtime needs no egress).
ADD --chmod=644 https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar /build/postgresql.jar

COPY ./src/order-ledger/OrderLedger.java .
RUN javac -cp /build/postgresql.jar OrderLedger.java

# --- runtime ---
FROM eclipse-temurin:21-jre
WORKDIR /usr/src/app

# Splunk OpenTelemetry Java agent (CSA). Applied via JAVA_TOOL_OPTIONS in the
# k8s manifest, matching the other Java services in this fork.
ADD --chmod=644 https://repo1.maven.org/maven2/com/splunk/splunk-otel-javaagent-csa/2.27.0/splunk-otel-javaagent-csa-2.27.0.jar /usr/src/app/splunk-otel-javaagent-csa.jar

COPY --from=builder /build/OrderLedger.class /build/postgresql.jar /usr/src/app/

EXPOSE 8080
ENTRYPOINT ["java", "-cp", "/usr/src/app:/usr/src/app/postgresql.jar", "OrderLedger"]
