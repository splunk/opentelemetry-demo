// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

const pino = require('pino')
const { trace } = require('@opentelemetry/api')

// Splunk-compatible logger configuration
// Outputs JSON logs to stdout for collection by Universal Forwarder or HEC
const logger = pino({
  level: process.env.LOG_LEVEL || 'info',

  // Splunk-friendly timestamp format (ISO 8601)
  timestamp: () => `,"time":"${new Date().toISOString()}"`,

  // Mixin to add service context and OpenTelemetry trace context to every log
  mixin() {
    const span = trace.getActiveSpan()
    const spanContext = span?.spanContext()

    return {
      'service.name': process.env['OTEL_SERVICE_NAME'] || 'payment',
      'service.version': process.env['SERVICE_VERSION'] || '1.0.0',
      // Fallback chain. OTEL_RESOURCE_ATTRIBUTES rarely carries the
      // environment in k8s -- the collector injects it downstream via
      // resource/add_environment -- and ENVIRONMENT is not set on these pods,
      // so without WORKSHOP_ENV (workshop-secret key "env") every record
      // logged "unknown". Also accept deployment.environment.name, the
      // current semconv key.
      'deployment.environment': process.env['OTEL_RESOURCE_ATTRIBUTES']?.match(/deployment\.environment(?:\.name)?=([^,]+)/)?.[1] || process.env['ENVIRONMENT'] || process.env['WORKSHOP_ENV'] || 'unknown',
      // OpenTelemetry trace context for correlation in Splunk
      ...(spanContext && spanContext.traceId && {
        'trace_id': spanContext.traceId,
        'span_id': spanContext.spanId,
        'trace_flags': spanContext.traceFlags,
      })
    }
  },

  formatters: {
    // Map Pino log levels to Splunk severity
    level: (label, number) => {
      return {
        severity: label.toUpperCase(),
        level: number
      }
    },

    // Clean log object formatting
    log: (object) => {
      // Preserve all fields without modification
      return object
    }
  },

  // Splunk best practices: single-line JSON output
  messageKey: 'message',
  errorKey: 'error',

  // Serialize errors properly for Splunk
  serializers: {
    err: pino.stdSerializers.err,
    error: pino.stdSerializers.err,
    req: pino.stdSerializers.req,
    res: pino.stdSerializers.res,
  }
})

module.exports = logger;
