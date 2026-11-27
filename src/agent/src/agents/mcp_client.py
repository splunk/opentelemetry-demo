#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""MCP client that injects W3C trace context into each tool/list request.

The MCP HTTP session is long-lived, so HTTP instrumentors do not create a new
trace per tool call. Putting traceparent/baggage in MCP `_meta` lets the server
restore the agent span as parent of execute_tool spans.
"""

import logging
from contextlib import AsyncExitStack

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams
from opentelemetry import propagate


def _trace_metadata(meta=None):
    if meta is None:
        carrier = {}
    elif isinstance(meta, dict):
        carrier = dict(meta)
    else:
        carrier = dict(meta.model_dump(exclude_none=True))
    propagate.inject(carrier)
    return carrier


class TracedClientSession(ClientSession):
    async def call_tool(
        self,
        name,
        arguments=None,
        read_timeout_seconds=None,
        progress_callback=None,
        *,
        meta=None,
        **kwargs,
    ):
        return await super().call_tool(
            name,
            arguments,
            read_timeout_seconds,
            progress_callback,
            meta=_trace_metadata(meta),
            **kwargs,
        )

    async def list_tools(self, *, params=None):
        params = (
            params.model_copy() if params is not None else PaginatedRequestParams()
        )
        params.meta = _trace_metadata(params.meta)
        return await super().list_tools(params=params)


class MCPClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session = None

    async def connect_to_mcp_server(self, url):
        stream_context = streamable_http_client(url=url)
        read, write = await self.exit_stack.enter_async_context(stream_context)
        session_context = TracedClientSession(read, write)
        self.session = await self.exit_stack.enter_async_context(session_context)
        await self.session.initialize()

    async def cleanup(self):
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            logging.error("Error closing connection : %s", e)


def _tool_result_text(result):
    if getattr(result, "isError", False):
        return str(result)
    texts = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts) if texts else str(result)


async def load_mcp_tools(session):
    """LangChain tools that call through the traced MCP session."""
    listed = await session.list_tools()
    tools = []
    for mcp_tool in listed.tools:
        async def _run(tool_name=mcp_tool.name, **kwargs):
            result = await session.call_tool(tool_name, kwargs)
            return _tool_result_text(result)

        _run.__name__ = mcp_tool.name
        _run.__doc__ = mcp_tool.description or mcp_tool.name
        tools.append(
            StructuredTool.from_function(
                coroutine=_run,
                name=mcp_tool.name,
                description=mcp_tool.description or mcp_tool.name,
            )
        )
    return tools
