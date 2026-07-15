# Apps

| Directory | Language | Description |
|-----------|----------|-------------|
| `java-secureapp-loadgen/` | Java | Jetty app from secureapp-loadgen with in-container shared loadgen (`k8s/loadgen/`) |
| `python-secureapp-loadgen/` | Python | Flask Team Portal with pinned vulnerable libraries |
| `node-secureapp-loadgen/` | Node.js | Express app with `@splunk/otel` SecureApp instrumentation |

Each app is built by `k8s/deploy.sh` and deployed to namespace `unified-secureapp`.

## Java build

Build from the **Unified-v2 root** (Dockerfile copies `k8s/loadgen/` scripts):

```bash
cd Unified-v2
docker build -f apps/java-secureapp-loadgen/Dockerfile -t secureapp/java-app:local .
```

Skip Maven (pre-built jar in `target/`):

```bash
docker build -f apps/java-secureapp-loadgen/Dockerfile \
  --build-arg SKIP_BUILD=true \
  -t secureapp/java-app:local .
```

## Python / Node build

```bash
docker build -t secureapp/python-app:local apps/python-secureapp-loadgen
docker build -t secureapp/node-app:local apps/node-secureapp-loadgen
```
