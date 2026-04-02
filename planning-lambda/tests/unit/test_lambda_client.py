# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/lambda_client.py."""

import json
import pytest
from unittest.mock import MagicMock, patch

from shared.lambda_client import invoke_lambda, invoke_lambda_async, get_lambda_client
from shared.tracing import init_tracer


class TestGetLambdaClient:
    """Tests for get_lambda_client function."""

    def test_get_lambda_client_creates_client(self, mock_boto3_lambda):
        """Creates boto3 Lambda client."""
        with patch('shared.lambda_client.boto3.client') as mock_boto:
            mock_boto.return_value = mock_boto3_lambda
            client = get_lambda_client()
            assert client is not None
            mock_boto.assert_called_once()

    def test_get_lambda_client_reuses_client(self, mock_boto3_lambda):
        """Reuses existing client on subsequent calls."""
        with patch('shared.lambda_client.boto3.client') as mock_boto:
            mock_boto.return_value = mock_boto3_lambda
            client1 = get_lambda_client()
            client2 = get_lambda_client()
            assert client1 is client2


class TestInvokeLambda:
    """Tests for invoke_lambda function."""

    def test_invoke_lambda_success(self):
        """Successful invoke with mocked boto3."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 200,
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = json.dumps({
                "statusCode": 200,
                "body": {"result": "success"}
            }).encode('utf-8')
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = invoke_lambda(
                "test-function",
                {"key": "value"}
            )

            assert result is not None
            mock_client.invoke.assert_called_once()

    def test_invoke_lambda_injects_trace_context(self):
        """Headers include traceparent."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 200,
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = json.dumps({}).encode('utf-8')
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            invoke_lambda("test-function", {"data": "test"}, propagate_context=True)

            # Verify payload was passed with trace context
            call_args = mock_client.invoke.call_args
            payload = json.loads(call_args.kwargs['Payload'].decode('utf-8'))
            assert "_trace_context" in payload

    def test_invoke_lambda_without_trace_context(self):
        """No trace context when propagate_context=False."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 200,
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = json.dumps({}).encode('utf-8')
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            invoke_lambda("test-function", {"data": "test"}, propagate_context=False)

            call_args = mock_client.invoke.call_args
            payload = json.loads(call_args.kwargs['Payload'].decode('utf-8'))
            assert "_trace_context" not in payload

    def test_invoke_lambda_handles_function_error(self):
        """Handles Lambda function errors gracefully."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 200,
                'FunctionError': 'Unhandled',
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = json.dumps({
                "errorMessage": "Something went wrong",
                "errorType": "Error"
            }).encode('utf-8')
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(Exception) as exc_info:
                invoke_lambda("test-function", {"data": "test"})

            assert "Lambda function error" in str(exc_info.value)

    def test_invoke_lambda_async_invocation(self):
        """Async invocation returns None."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 202,
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = b''
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = invoke_lambda(
                "test-function",
                {"data": "test"},
                invocation_type="Event"
            )

            assert result is None
            call_args = mock_client.invoke.call_args
            assert call_args.kwargs['InvocationType'] == 'Event'


class TestInvokeLambdaAsync:
    """Tests for invoke_lambda_async helper."""

    def test_invoke_lambda_async_calls_invoke(self):
        """invoke_lambda_async calls invoke_lambda with Event type."""
        init_tracer("test-service")

        with patch('shared.lambda_client.get_lambda_client') as mock_get_client:
            mock_client = MagicMock()
            mock_response = {
                'StatusCode': 202,
                'Payload': MagicMock()
            }
            mock_response['Payload'].read.return_value = b''
            mock_client.invoke.return_value = mock_response
            mock_get_client.return_value = mock_client

            invoke_lambda_async("test-function", {"data": "test"})

            call_args = mock_client.invoke.call_args
            assert call_args.kwargs['InvocationType'] == 'Event'
