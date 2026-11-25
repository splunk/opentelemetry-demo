// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { context, SpanStatusCode, trace } from '@opentelemetry/api';

/**
 * Run work as a Splunk RUM custom workflow so child fetches (e.g. POST
 * /api/checkout) sit under the custom event and can continue into APM.
 * window.tracer is set in _document.tsx from SplunkRum.provider.
 */
export async function withWorkflowSpan<T>(
  name: string,
  attributes: Record<string, string | number | boolean>,
  fn: () => Promise<T>
): Promise<T> {
  if (typeof window === 'undefined') {
    return fn();
  }

  const tracer = (window as Window & { tracer?: ReturnType<typeof trace.getTracer> }).tracer;
  if (!tracer) {
    return fn();
  }

  const span = tracer.startSpan(name, {
    attributes: {
      'workflow.name': name,
      ...attributes,
    },
  });

  try {
    return await context.with(trace.setSpan(context.active(), span), fn);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    span.setStatus({ code: SpanStatusCode.ERROR, message });
    if (err instanceof Error) {
      span.recordException(err);
    }
    throw err;
  } finally {
    span.end();
  }
}
