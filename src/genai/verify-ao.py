# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Run inside an instrumented agent pod to check a real prompt and AO acknowledgement.

    kubectl exec -i deploy/agent -- python - < src/genai/verify-ao.py
"""

import json
import os
import uuid
from dataclasses import asdict

import requests
from genai.agent_observability import conversation_context
from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from splunk_ao.otel import add_splunk_ao_span_processor

provider = TracerProvider(resource=Resource.create({
    "service.name": "agent-observability-check",
}))
processor = add_splunk_ao_span_processor(provider)
trace.set_tracer_provider(provider)
session_id = f"sao-check-{uuid.uuid4()}"
prompt = "Show all available products in the store."

try:
    with conversation_context(session_id):
        with provider.get_tracer("astronomy-shop-check").start_as_current_span(
            "invoke_workflow astronomy_shop_smoke_check",
            attributes={
                "gen_ai.operation.name": "invoke_workflow",
                "gen_ai.workflow.name": "astronomy_shop_smoke_check",
                "gen_ai.input.messages": json.dumps([
                    {"role": "user", "parts": [{"type": "text", "content": prompt}]}
                ]),
            },
        ) as span:
            carrier = {}
            propagate.inject(carrier)
            response = requests.post(
                f"http://agent:{os.getenv('AGENT_PORT', '8010')}/prompt",
                json={"message": prompt, "history": [], "session_id": session_id},
                headers=carrier,
                timeout=120,
            )
            response.raise_for_status()
            messages = response.json()["response"]["messages"]
            span.set_attribute("gen_ai.output.messages", json.dumps([
                {"role": "assistant", "parts": [
                    {"type": "text", "content": messages[-1]["content"]}
                ]}
            ]))
            print(json.dumps({
                "http_status": response.status_code,
                "trace_id": f"{span.get_span_context().trace_id:032x}",
                "conversation_id": session_id,
                "tool_results": [
                    {"name": m.get("name"), "status": m.get("status")}
                    for m in messages if m.get("type") == "tool"
                ],
                "answer_characters": len(messages[-1]["content"]),
            }))
    provider.force_flush(timeout_millis=30000)
    print(json.dumps({"ao_export": asdict(processor.export_health)}))
    if processor.export_health.healthy is not True:
        raise SystemExit("Agent Observability did not acknowledge this check as accepted.")
finally:
    provider.shutdown()
