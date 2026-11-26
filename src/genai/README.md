# Shared GenAI client

Pinned from `open-telemetry/opentelemetry-demo` (`src/genai/UPSTREAM-SHA`).

`ChatLLM` (LangChain `ChatOpenAI` + VCR) is the OpenAI-compatible client used by
the Astronomy Shop **agent**. Plan B will point **product-reviews** at this
same package so both services share one venv-style LLM stack.

| Env | Default (agent k8s) | Purpose |
|---|---|---|
| `USE_VCR` | `true` | Replay `fixtures/vcr_cassettes/{LLM_MODEL}_cassette.yaml` |
| `LLM_MODEL` | `claude-opus-4-7` | Cassette name (`/` → `_`) |
| `LLM_BASE_URL` | `https://local-llm.com` | Unused while VCR is on |
| `API_KEY` | `sk-dummy` | Required by the OpenAI SDK; dummy is fine with VCR |
| `VCR_CASSETTE_DIR` | this package's `fixtures/vcr_cassettes` | Override cassette path |
| `VCR_MATCH_THRESHOLD` | `0.85` | Fuzzy body match so MCP-wrapped tools still replay |

Do not reuse the product-reviews mock vars (`LLM_MODEL=astronomy-llm`,
`LLM_BASE_URL=http://llm:8000/v1`) on the agent. Those stay on `llm` /
`product-reviews` until Plan B.

## Splunk Agent Observability

`agent_observability.py` attaches `splunk-ao==0.7.0` after Traceloop/OTLP so
APM still goes to the node collector. SAO is a second export.

| Env | k8s default | Purpose |
|---|---|---|
| `SPLUNK_AO_ENABLED` | `true` | Off = collector only. Missing secrets skip SAO (pod still starts). |
| `SPLUNK_AO_REALM` | `workshop-secret/realm` | e.g. `us1` |
| `SPLUNK_AO_O11Y_TOKEN` | `workshop-secret/access_token` | ingest token |
| `SPLUNK_AO_PROJECT` / `SPLUNK_AO_AGENT_STREAM` | `opentelemetry-demo` | override per shop |
| `TRACELOOP_TRACE_CONTENT` | `true` | prompt/tool content on spans |

MCP tool calls carry `traceparent` in `_meta` so execute_tool spans stay on the
agent trace. Chatbot sends `session_id` as `gen_ai.conversation.id`.

Smoke check (after images are up):

```sh
kubectl exec -i deploy/agent -- python - < src/genai/verify-ao.py
```
