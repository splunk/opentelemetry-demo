# =====================================================================
# Unified SecureApp loadgen — one Dockerfile, three language targets.
# Build via: docker build --target={java|node|python} -f <this> .
# Context: repo root.
#
# Add a 4th language:
#   1. Add a runtime target `FROM <base> AS <lang>` below (mirror pattern)
#   2. Add matching svc entry to services.yaml with build_target: <lang>
#   3. Add matching Deployment+Service to secureapp-loadgen-k8s.yaml
# =====================================================================

# ---------------------------------------------------------------------
# JAVA — build stage (Maven → jar)
# ---------------------------------------------------------------------
FROM maven:3.9-eclipse-temurin-17 AS java-builder
ARG SKIP_BUILD=false
WORKDIR /build
COPY src/secureapp-loadgen/unified-v2/apps/java-secureapp-loadgen/pom.xml .
RUN if [ "$SKIP_BUILD" = "false" ]; then mvn dependency:go-offline -B; fi
COPY src/secureapp-loadgen/unified-v2/apps/java-secureapp-loadgen/src src
RUN if [ "$SKIP_BUILD" = "false" ]; then \
      mvn clean package -B -DskipTests; \
    else \
      mkdir -p target; \
    fi

# ---------------------------------------------------------------------
# JAVA — runtime target
# ---------------------------------------------------------------------
FROM eclipse-temurin:17-jre AS java
ARG SPLUNK_OTEL_JAVAAGENT_VERSION=2.27.0
ARG SPLUNK_OTEL_JAVAAGENT_URL=
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates bash \
    && if [ -n "${SPLUNK_OTEL_JAVAAGENT_URL}" ]; then \
         curl -fsSL "${SPLUNK_OTEL_JAVAAGENT_URL}" -o splunk-otel-javaagent.jar; \
       else \
         curl -fsSL \
           "https://repo1.maven.org/maven2/com/splunk/splunk-otel-javaagent-csa/${SPLUNK_OTEL_JAVAAGENT_VERSION}/splunk-otel-javaagent-csa-${SPLUNK_OTEL_JAVAAGENT_VERSION}.jar" \
           -o splunk-otel-javaagent.jar; \
       fi \
    && test -s splunk-otel-javaagent.jar \
    && rm -rf /var/lib/apt/lists/*
COPY --from=java-builder /build/target/java-secureapp-test-app.jar .
COPY src/secureapp-loadgen/unified-v2/apps/java-secureapp-loadgen/entrypoint.sh .
COPY src/secureapp-loadgen/unified-v2/k8s/loadgen/loadgen.sh src/secureapp-loadgen/unified-v2/k8s/loadgen/loadgen-entries.sh ./
RUN chmod +x entrypoint.sh loadgen.sh loadgen-entries.sh
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318 \
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_METRICS_EXPORTER=otlp \
    LOADGEN_LANGUAGE=java
EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]

# ---------------------------------------------------------------------
# NODE — runtime target (no separate build stage; npm install in place)
# ---------------------------------------------------------------------
FROM node:20-bookworm-slim AS node
WORKDIR /app
# python3/make/g++ needed for better-sqlite3 native module build
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 make g++ curl \
    && rm -rf /var/lib/apt/lists/*
COPY src/secureapp-loadgen/unified-v2/apps/node-secureapp-loadgen/package.json ./
RUN npm install --omit=dev
COPY src/secureapp-loadgen/unified-v2/apps/node-secureapp-loadgen/src ./src
ENV SERVER_PORT=8080 \
    SPLUNK_SECUREAPP_AGENT_ENABLED=true \
    SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=60 \
    SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL=86400000 \
    SPLUNK_SECUREAPP_RUNTIME_PACKAGES_ONLY=true \
    SPLUNK_SECUREAPP_NO_SELF_REPORT=false \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318 \
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://collector:4318/v1/logs \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=otlp \
    OTEL_LOGS_EXPORTER=otlp
EXPOSE 8080
CMD ["node", "-r", "@splunk/otel/instrument.js", "src/server.js"]

# ---------------------------------------------------------------------
# PYTHON — runtime target
# ---------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS python
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY src/secureapp-loadgen/unified-v2/apps/python-secureapp-loadgen/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/secureapp-loadgen/unified-v2/apps/python-secureapp-loadgen/src ./src
COPY src/secureapp-loadgen/unified-v2/apps/python-secureapp-loadgen/run.py .
COPY src/secureapp-loadgen/unified-v2/apps/python-secureapp-loadgen/gunicorn.conf.py .
ENV SERVER_PORT=8080 \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318 \
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://collector:4318/v1/logs \
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=otlp \
    OTEL_LOGS_EXPORTER=otlp \
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=false \
    SPLUNK_SECUREAPP_AGENT_ENABLED=true \
    SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=60 \
    SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL=86400
EXPOSE 8080
CMD ["opentelemetry-instrument", \
     "gunicorn", \
     "-c", "gunicorn.conf.py", \
     "run:app"]
