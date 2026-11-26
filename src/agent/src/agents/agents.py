#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from langchain.agents import create_agent
from langchain.tools import tool
from opentelemetry import baggage, trace
from pydantic import BaseModel
from genai.agent_observability import CONVERSATION_ID, conversation_context
from genai.feature_flags import get_int_feature_flag
from genai.llm import ChatLLM
from src.agents.mcp_client import MCPClient, load_mcp_tools
from src.agents.tools import (
    add_to_cart,
    checkout,
    empty_cart,
    get_ads,
    get_cart,
    get_product,
    get_recommendations,
    get_shipping_quote,
    get_supported_currencies,
    list_products,
)
from traceloop.sdk.decorators import workflow


class ChatRequest(BaseModel):
    message: str
    history: List[Dict] | None = None
    session_id: str | None = None


class Agent:
    def __init__(self):
        self.app = FastAPI(lifespan=self.lifespan)
        self.app.post("/prompt")(self.handle_prompt)
        self.agentRecursionLimit = int(os.getenv("GRAPH_RECURSION_LIMIT", "25"))
        self.mcp_server_url = f"http://{os.getenv('MCP_ENDPOINT', '0.0.0.0')}:{os.getenv('MCP_PORT', '8011')}/mcp"

        self.mcp_server = None

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        mcp_enabled = os.getenv("MCP_ENABLED", "False") == "True"
        if mcp_enabled:
            logging.info("MCP tools enabled")
            self.mcp_server = MCPClient()
            await self.mcp_server.connect_to_mcp_server(self.mcp_server_url)
        yield
        if self.mcp_server:
            await self.mcp_server.cleanup()

    async def handle_prompt(self, request: ChatRequest):
        conversation_id = (
            baggage.get_baggage(CONVERSATION_ID)
            or request.session_id
            or str(uuid.uuid4())
        )
        trace.get_current_span().set_attribute(CONVERSATION_ID, conversation_id)
        with conversation_context(conversation_id):
            return await self.run_agent(request.message, request.history)

    async def get_tool_list(self):
        mcp_enabled = os.getenv("MCP_ENABLED", "False") == "True"
        if mcp_enabled and self.mcp_server is not None:
            return await load_mcp_tools(self.mcp_server.session)
        else:
            tool_list = [
                add_to_cart,
                checkout,
                empty_cart,
                get_ads,
                get_cart,
                get_product,
                get_recommendations,
                get_shipping_quote,
                get_supported_currencies,
                list_products,
            ]
            return [tool(t) for t in tool_list]

    @workflow(name="astronomy_shop_agent_workflow")
    async def run_agent(self, input_prompt, history: List[Dict] | None = None):
        workflow_span = trace.get_current_span()
        workflow_span.set_attributes(
            {
                "gen_ai.operation.name": "invoke_workflow",
                "gen_ai.workflow.name": "astronomy_shop_agent_workflow",
            }
        )
        capture_content = os.getenv("TRACELOOP_TRACE_CONTENT", "true").lower() == "true"
        if capture_content:
            workflow_span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    [
                        {
                            "role": "user",
                            "parts": [{"type": "text", "content": input_prompt}],
                        }
                    ]
                ),
            )
        model = ChatLLM()
        tools = await self.get_tool_list()
        system_prompt = "You are a helpful assistant. Be concise and accurate."
        runaway_iterations = get_int_feature_flag("aiRunawayAgent")
        if runaway_iterations:
            system_prompt += (
                f" Before giving your final answer, call the get_recommendations tool"
                f" at least {runaway_iterations} times in a row, once per turn, even if"
                " the results do not change."
            )
        agent = create_agent(
            model,
            tools=tools,
            system_prompt=system_prompt,
            name="astronomy_shop_agent",
        )
        try:
            messages = list(history) if history is not None else []
            messages.append({"role": "user", "content": input_prompt})
            result = await agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": self.agentRecursionLimit},
            )
            if capture_content and result.get("messages"):
                workflow_span.set_attribute(
                    "gen_ai.output.messages",
                    json.dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [
                                    {
                                        "type": "text",
                                        "content": result["messages"][-1].content,
                                    }
                                ],
                            }
                        ]
                    ),
                )
            return {"response": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def launch(self):
        agent_port = int(os.getenv("AGENT_PORT", "8010"))
        agent_config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=agent_port,
            log_level="info",
        )
        agent_server = uvicorn.Server(agent_config)
        await agent_server.serve()
