# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import importlib.util
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn
from genai.agent_observability import (
    CONVERSATION_ID,
    ConversationExportProcessor,
    ConversationSpanProcessor,
    configure_agent_observability,
    conversation_context,
)
from fastmcp import FastMCP
from opentelemetry import baggage, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client_module = load_module("mcp_client", "src/agent/src/agents/mcp_client.py")
server_module = load_module("mcp_telemetry", "src/mcp/src/mcp_server/telemetry.py")
shop_tools = load_module("shop_tools", "src/shared/tools.py")
provider = TracerProvider()
exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(exporter))
provider.add_span_processor(ConversationSpanProcessor())
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("agent-observability-tests")


class ExportTests(unittest.TestCase):
    def test_conversation_export_includes_non_llm_root_and_http_spans(self):
        local = TracerProvider()
        collector = InMemorySpanExporter()
        ao = InMemorySpanExporter()
        local.add_span_processor(ConversationSpanProcessor())
        local.add_span_processor(SimpleSpanProcessor(collector))
        local.add_span_processor(ConversationExportProcessor(SimpleSpanProcessor(ao)))
        tracer = local.get_tracer("load-generator")
        with tracer.start_as_current_span("ordinary_shopping_request"):
            pass
        with conversation_context("agent-conversation"):
            with tracer.start_as_current_span("user_ask_agent") as root:
                with tracer.start_as_current_span("POST"):
                    pass
        with tracer.start_as_current_span("another_shopping_request"):
            pass
        spans = ao.get_finished_spans()
        self.assertEqual([span.name for span in spans], ["POST", "user_ask_agent"])
        self.assertEqual(spans[0].parent.span_id, root.get_span_context().span_id)
        self.assertIsNone(spans[1].parent)
        self.assertEqual(len(collector.get_finished_spans()), 4)
        self.assertTrue(local.force_flush())
        local.shutdown()

    def test_missing_config_skips_export(self):
        with patch.dict(os.environ, {"SPLUNK_AO_ENABLED": "true"}, clear=True):
            self.assertIsNone(configure_agent_observability())

    def test_conversation_context_restores_after_error(self):
        with conversation_context("outer"):
            try:
                with conversation_context("inner"):
                    raise ValueError("test")
            except ValueError:
                pass
            self.assertEqual(baggage.get_baggage(CONVERSATION_ID), "outer")
        self.assertIsNone(baggage.get_baggage(CONVERSATION_ID))


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        exporter.clear()
        mcp = FastMCP("test-shop")
        mcp.add_middleware(server_module.TraceContextMiddleware())

        @mcp.tool()
        @shop_tools.count_tool_call
        async def echo(value: str):
            """Echo the requested value."""
            await asyncio.sleep(0.01)
            return value

        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(mcp.http_app(), log_level="error"))
        self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
        async with asyncio.timeout(10):
            while not self.server.started:
                if self.task.done():
                    self.task.result()
                await asyncio.sleep(0.01)

    async def asyncTearDown(self):
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 10)
        self.sock.close()

    async def test_shared_mcp_connection_keeps_concurrent_conversations_separate(self):
        client = client_module.MCPClient()
        await client.connect_to_mcp_server(f"http://127.0.0.1:{self.port}/mcp")
        try:

            async def invoke(session_id):
                with conversation_context(session_id):
                    with tracer.start_as_current_span("agent") as parent:
                        await client.session.list_tools()
                        await client.session.call_tool("echo", {"value": session_id})
                        return parent.get_span_context()

            parents = await asyncio.gather(
                invoke("conversation-a"), invoke("conversation-b")
            )
            spans = exporter.get_finished_spans()
            tools = [
                s
                for s in spans
                if s.attributes.get("gen_ai.operation.name") == "execute_tool"
            ]
            self.assertEqual(len(tools), 2)
            for parent, session_id in zip(
                parents, ("conversation-a", "conversation-b")
            ):
                span = next(
                    s for s in tools if s.attributes[CONVERSATION_ID] == session_id
                )
                self.assertEqual(span.context.trace_id, parent.trace_id)
                self.assertEqual(span.parent.span_id, parent.span_id)
                self.assertEqual(
                    span.attributes["gen_ai.tool.call.result"], f'"{session_id}"'
                )
                self.assertEqual(span.attributes["gen_ai.tool.name"], "echo")
            self.assertIsNone(baggage.get_baggage(CONVERSATION_ID))
        finally:
            await client.cleanup()

    async def test_tool_errors_and_content_opt_out(self):
        @shop_tools.count_tool_call
        async def failing_tool():
            return "Error fetching products: unavailable"

        with patch.dict(os.environ, {"TRACELOOP_TRACE_CONTENT": "false"}):
            with tracer.start_as_current_span("tool"):
                await failing_tool()
        span = exporter.get_finished_spans()[-1]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertNotIn("gen_ai.tool.call.result", span.attributes)


if __name__ == "__main__":
    unittest.main()
