# SecureApp loadgen — Java vulnerability test app + randomized attack trigger.
# Exercises 5 vulnerability classes (RCE, SSRF, SQLi, Log4Shell, Deserialization)
# detected by the Splunk OTel Java agent's SecureApp feature.
#
# To skip Maven build and use a pre-built jar:
#   docker build --build-arg SKIP_BUILD=true -f src/secureapp-loadgen/Dockerfile .

# --- Build stage ---
FROM maven:3.9-eclipse-temurin-17 AS builder
ARG SKIP_BUILD=false
WORKDIR /build

COPY ./src/secureapp-loadgen/pom.xml .
RUN if [ "$SKIP_BUILD" = "false" ]; then mvn dependency:go-offline -B; fi

COPY ./src/secureapp-loadgen/src src
RUN if [ "$SKIP_BUILD" = "false" ]; then \
      mvn clean package -B -DskipTests; \
    else \
      mkdir -p target; \
    fi

# --- Runtime stage ---
FROM eclipse-temurin:17-jre

# Splunk OTel Java agent — CSA build (Cisco Secure Application) includes SecureApp/Argento hooks
ADD --chmod=644 https://repo1.maven.org/maven2/com/splunk/splunk-otel-javaagent-csa/2.27.0/splunk-otel-javaagent-csa-2.27.0.jar /app/splunk-otel-javaagent.jar

WORKDIR /app

# Install curl for the loadgen script
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/java-secureapp-test-app.jar .
COPY ./src/secureapp-loadgen/entrypoint.sh .
COPY ./src/secureapp-loadgen/loadgen.sh .
RUN chmod +x entrypoint.sh loadgen.sh

ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENV OTEL_METRICS_EXPORTER=otlp

EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
