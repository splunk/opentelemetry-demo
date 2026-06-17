# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""AWS Lambda invocation client with OpenTelemetry tracing."""

import json
import os
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config

from opentelemetry.trace import SpanKind

from .tracing import create_span, inject_context
from .logging import get_logger
from .env import for_invoke, STAMPED_ATTR, tag as tag_env

logger = get_logger(__name__)

# Lambda client with retry configuration
_lambda_client = None


def get_lambda_client():
    """Get or create the Lambda client."""
    global _lambda_client
    if _lambda_client is None:
        config = Config(
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            },
            connect_timeout=5,
            read_timeout=60
        )
        _lambda_client = boto3.client('lambda', config=config)
    return _lambda_client


def invoke_lambda(
    function_name: str,
    payload: Dict[str, Any],
    invocation_type: str = "RequestResponse",
    propagate_context: bool = True,
    env_raw: Optional[str] = None,
    peer_service: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Invoke another Lambda function with trace context + env propagation.

    Args:
        function_name: Lambda function name or ARN.
        payload: Request payload to send.
        invocation_type: 'RequestResponse' (sync) or 'Event' (async).
        propagate_context: Whether to propagate trace context.
        env_raw: Bare source env (e.g. "dev-astronomy"). When set, packed into
            ClientContext.custom["env"] so the invoked Lambda can stamp its own
            telemetry with the same env for gateway-collector routing.
        peer_service: OTel `service.name` of the target Lambda. Stamped as
            `peer.service` on the outgoing client span so Splunk APM draws a
            service-map edge from this Lambda to the target. Defaults to the
            function name basename when omitted.

    Returns:
        Response payload for sync invocations, None for async.

    Raises:
        Exception: If Lambda invocation fails.
    """
    client = get_lambda_client()

    # Create span for the outgoing Lambda call
    span_attributes = {
        "faas.invoked_name": function_name,
        "faas.invoked_provider": "aws",
        "faas.invocation_type": invocation_type.lower(),
        "peer.service": peer_service or function_name.split(":")[-1],
    }
    if env_raw:
        span_attributes[STAMPED_ATTR] = tag_env(env_raw)

    with create_span(
        f"Lambda.Invoke.{function_name.split(':')[-1]}",
        kind=SpanKind.CLIENT,
        attributes=span_attributes
    ) as span:
        # Inject trace context into payload if enabled
        if propagate_context:
            headers = inject_context()
            payload = {
                **payload,
                "_trace_context": headers
            }

        # Build ClientContext carrying env + trace headers (custom values must be strings).
        invoke_kwargs: Dict[str, Any] = {
            "FunctionName": function_name,
            "InvocationType": invocation_type,
            "Payload": json.dumps(payload).encode('utf-8'),
        }
        if env_raw:
            invoke_kwargs["ClientContext"] = for_invoke(
                env_raw,
                extra=headers if propagate_context else None,
            )

        logger.info(
            f"Invoking Lambda: {function_name}",
            extra={
                "function_name": function_name,
                "invocation_type": invocation_type,
                "payload_size": len(json.dumps(payload)),
                "env": env_raw or "unset",
            }
        )

        try:
            response = client.invoke(**invoke_kwargs)

            status_code = response.get('StatusCode', 0)
            span.set_attribute("http.status_code", status_code)

            # Check for function errors
            if 'FunctionError' in response:
                error_type = response['FunctionError']
                span.set_attribute("faas.error_type", error_type)
                error_payload = json.loads(response['Payload'].read().decode('utf-8'))
                logger.error(
                    f"Lambda function error: {error_type}",
                    extra={
                        "function_name": function_name,
                        "error_type": error_type,
                        "error_payload": error_payload
                    }
                )
                raise Exception(f"Lambda function error: {error_type} - {error_payload}")

            # For async invocations, no response payload
            if invocation_type == "Event":
                logger.info(
                    f"Lambda invoked asynchronously: {function_name}",
                    extra={"function_name": function_name, "status_code": status_code}
                )
                return None

            # Parse response payload
            response_payload = json.loads(response['Payload'].read().decode('utf-8'))

            logger.info(
                f"Lambda invocation successful: {function_name}",
                extra={
                    "function_name": function_name,
                    "status_code": status_code,
                    "response_size": len(json.dumps(response_payload))
                }
            )

            return response_payload

        except client.exceptions.ResourceNotFoundException:
            logger.error(f"Lambda function not found: {function_name}")
            span.set_attribute("error.type", "ResourceNotFoundException")
            raise
        except client.exceptions.InvalidRequestContentException as e:
            logger.error(f"Invalid request to Lambda: {e}")
            span.set_attribute("error.type", "InvalidRequestContentException")
            raise
        except Exception as e:
            logger.error(f"Lambda invocation failed: {e}")
            raise


def invoke_lambda_async(
    function_name: str,
    payload: Dict[str, Any],
    propagate_context: bool = True,
    env_raw: Optional[str] = None,
    peer_service: Optional[str] = None,
) -> None:
    """
    Invoke Lambda function asynchronously.

    Args:
        function_name: Lambda function name or ARN.
        payload: Request payload to send.
        propagate_context: Whether to propagate trace context.
        env_raw: Bare source env (see invoke_lambda).
        peer_service: OTel service.name of the target (see invoke_lambda).
    """
    invoke_lambda(
        function_name=function_name,
        payload=payload,
        invocation_type="Event",
        propagate_context=propagate_context,
        env_raw=env_raw,
        peer_service=peer_service,
    )
