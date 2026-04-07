# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for Lambda testing."""

import json
import os
import sys
from unittest.mock import MagicMock, patch
from typing import Dict, Any

import pytest

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Planning_Init'))


@pytest.fixture(autouse=True)
def reset_tracer():
    """Reset the global tracer before each test."""
    from shared import tracing
    tracing._tracer = None
    yield
    tracing._tracer = None


@pytest.fixture(autouse=True)
def reset_lambda_client():
    """Reset the global Lambda client before each test."""
    from shared import lambda_client
    lambda_client._lambda_client = None
    yield
    lambda_client._lambda_client = None


@pytest.fixture
def mock_lambda_context():
    """Mock AWS Lambda context object."""
    context = MagicMock()
    context.function_name = "Planning_Init"
    context.function_version = "$LATEST"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:Planning_Init"
    context.memory_limit_in_mb = 128
    context.aws_request_id = "test-request-id-12345"
    context.log_group_name = "/aws/lambda/Planning_Init"
    context.log_stream_name = "2024/01/15/[$LATEST]abc123"
    context.get_remaining_time_in_millis = MagicMock(return_value=30000)
    return context


@pytest.fixture
def sample_traceparent():
    """Valid W3C traceparent header."""
    return "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


@pytest.fixture
def sample_headers(sample_traceparent):
    """Sample API Gateway headers with trace context."""
    return {
        "traceparent": sample_traceparent,
        "Content-Type": "application/json",
        "Host": "api.example.com",
    }


@pytest.fixture
def sample_api_gateway_event(sample_headers):
    """Sample API Gateway HTTP v2 event."""
    return {
        "version": "2.0",
        "routeKey": "POST /orders",
        "rawPath": "/orders",
        "rawQueryString": "",
        "headers": sample_headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "api123",
            "domainName": "api.example.com",
            "domainPrefix": "api",
            "http": {
                "method": "POST",
                "path": "/orders",
                "protocol": "HTTP/1.1",
                "sourceIp": "192.168.1.1",
                "userAgent": "TestAgent/1.0"
            },
            "requestId": "test-request-id",
            "routeKey": "POST /orders",
            "stage": "$default",
            "time": "15/Jan/2024:10:30:00 +0000",
            "timeEpoch": 1705314600000
        },
        "body": None,
        "isBase64Encoded": False
    }


@pytest.fixture
def sample_orders_payload():
    """Sample orders payload from K8s planning service."""
    return {
        "service": "planning",
        "timestamp": "2024-01-15T10:30:00Z",
        "orders_count": 2,
        "orders": [
            {
                "order_id": "ORD-001",
                "items_count": 3,
                "shipping_tracking_id": "TRK-001",
                "processed_at": "2024-01-15T10:29:00Z",
                "shipping_address": {
                    "street_address": "123 Main St",
                    "city": "New York",
                    "state": "NY",
                    "country": "US",
                    "zip_code": "10001"
                },
                "shipping_cost": {
                    "units": 25,
                    "nanos": 0,
                    "currency_code": "USD"
                }
            },
            {
                "order_id": "ORD-002",
                "items_count": 7,
                "shipping_tracking_id": "TRK-002",
                "processed_at": "2024-01-15T10:29:30Z",
                "shipping_address": {
                    "street_address": "456 High St",
                    "city": "London",
                    "country": "GB",
                    "zip_code": "SW1A 1AA"
                },
                "shipping_cost": {
                    "units": 75,
                    "nanos": 500000000,
                    "currency_code": "GBP"
                }
            }
        ]
    }


@pytest.fixture
def api_event_with_orders(sample_api_gateway_event, sample_orders_payload):
    """API Gateway event with orders payload in body."""
    event = sample_api_gateway_event.copy()
    event["body"] = json.dumps(sample_orders_payload)
    return event


@pytest.fixture
def mock_boto3_lambda():
    """Mock boto3 Lambda client."""
    with patch('boto3.client') as mock_client:
        mock_lambda = MagicMock()
        mock_client.return_value = mock_lambda

        # Default successful response
        mock_response = {
            'StatusCode': 200,
            'Payload': MagicMock()
        }
        mock_response['Payload'].read.return_value = json.dumps({
            "statusCode": 200,
            "body": json.dumps({"status": "success"})
        }).encode('utf-8')
        mock_lambda.invoke.return_value = mock_response

        yield mock_lambda


@pytest.fixture
def env_vars():
    """Set and restore environment variables for testing."""
    original_env = os.environ.copy()

    # Set test environment variables
    test_env = {
        "OTEL_SERVICE_NAME": "test-planning-lambda",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "LOG_LEVEL": "DEBUG",
        "DOWNSTREAM_LAMBDA_ARN": "",
    }
    os.environ.update(test_env)

    yield test_env

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def capture_logs(capfd):
    """Capture and parse JSON log output."""
    class LogCapture:
        def get_logs(self):
            """Get captured log entries as parsed JSON."""
            out, _ = capfd.readouterr()
            logs = []
            for line in out.strip().split('\n'):
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return logs

    return LogCapture()
