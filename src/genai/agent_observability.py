# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Optional Splunk Agent Observability export alongside the existing collector.

Ported from timhard-splunk/opentelemetry-demo feat/splunk-agent-observability
(0318166a). Collector/APM export stays; SAO is an extra span processor.
"""

import logging
import os
from contextlib import contextmanager

from opentelemetry import baggage, context, trace
from opentelemetry.sdk.trace import SpanProcessor

CONVERSATION_ID = "gen_ai.conversation.id"


class ConversationSpanProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None):
        conversation_id = baggage.get_baggage(CONVERSATION_ID, context=parent_context)
        if conversation_id:
            span.set_attribute(CONVERSATION_ID, conversation_id)


class ConversationExportProcessor(SpanProcessor):
    """Export all spans of agent conversations, including non-LLM parents."""

    def __init__(self, delegate):
        self.delegate = delegate

    def on_start(self, span, parent_context=None):
        self.delegate.on_start(span, parent_context)

    def on_end(self, span):
        if span.attributes.get(CONVERSATION_ID):
            self.delegate.on_end(span)

    def force_flush(self, timeout_millis=30000):
        return self.delegate.force_flush(timeout_millis)

    def shutdown(self):
        self.delegate.shutdown()


def configure_agent_observability(*, only_conversations=False):
    provider = trace.get_tracer_provider()
    provider.add_span_processor(ConversationSpanProcessor())
    if os.getenv("SPLUNK_AO_ENABLED", "false").lower() != "true":
        return None
    if os.getenv("SPLUNK_AO_LOGGING_DISABLED", "false").lower() == "true":
        return None

    required = (
        "SPLUNK_AO_REALM",
        "SPLUNK_AO_O11Y_TOKEN",
        "SPLUNK_AO_PROJECT",
        "SPLUNK_AO_AGENT_STREAM",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        # Shops without workshop-secret still start; SAO is skipped.
        logging.error(
            "Agent Observability enabled but missing %s; skipping AO export",
            ", ".join(missing),
        )
        return None

    from splunk_ao.otel import SplunkAOSpanProcessor, add_splunk_ao_span_processor

    processor = SplunkAOSpanProcessor()
    if only_conversations:
        provider.add_span_processor(ConversationExportProcessor(processor))
    else:
        add_splunk_ao_span_processor(provider, processor)
    logging.info(
        "Agent Observability enabled: realm=%s project=%s agent_stream=%s",
        os.environ["SPLUNK_AO_REALM"],
        os.environ["SPLUNK_AO_PROJECT"],
        os.environ["SPLUNK_AO_AGENT_STREAM"],
    )
    return processor


@contextmanager
def conversation_context(conversation_id):
    token = context.attach(baggage.set_baggage(CONVERSATION_ID, conversation_id))
    try:
        yield
    finally:
        context.detach(token)
