# Bash + curl runner for shared loadgen scripts in k8s datagen pods.
# Uses debian:bookworm-slim (same family as python/node app images — often already cached).
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /scripts
