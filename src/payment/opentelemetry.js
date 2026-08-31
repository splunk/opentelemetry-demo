// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

const { start } = require('@splunk/otel');
const {
  AlwaysOnSampler,
  ParentBasedSampler,
  SamplingDecision,
} = require('@opentelemetry/sdk-trace-base');

// The kubelet probes the gRPC health service on every liveness (10s) and
// readiness (5s) tick. Auto-instrumentation turns each probe into a SERVER
// span, so Splunk APM counts ~18 extra "requests" per minute per pod. With
// four payment pods that is ~360 phantom requests per 5 minutes, which buries
// the real Charge traffic and makes the error rate look far lower than the
// paymentFailure A/B split actually produces.
const HEALTH_CHECK_SPAN = /^grpc\.health\.v1\.Health\//;

class HealthCheckFilteringSampler {
  constructor(delegate) {
    this._delegate = delegate;
  }

  shouldSample(context, traceId, spanName, spanKind, attributes, links) {
    if (HEALTH_CHECK_SPAN.test(spanName)) {
      return { decision: SamplingDecision.NOT_RECORD };
    }
    return this._delegate.shouldSample(context, traceId, spanName, spanKind, attributes, links);
  }

  toString() {
    return `HealthCheckFiltering(${this._delegate.toString()})`;
  }
}

start({
  serviceName: process.env.OTEL_SERVICE_NAME || 'payment',
  tracing: {
    tracerConfig: {
      sampler: new HealthCheckFilteringSampler(
        new ParentBasedSampler({ root: new AlwaysOnSampler() })
      ),
    },
  },
});
