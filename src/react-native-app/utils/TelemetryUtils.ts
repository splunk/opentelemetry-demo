// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Telemetry Utilities for Splunk RUM in React Native
 * Provides helpers for creating custom spans, events, and error tracking
 * Ported from the frontend implementation
 */

import { SplunkRum } from "@splunk/otel-react-native";

/**
 * Get the global tracer instance from Splunk RUM
 * Returns null if RUM is not initialized
 */
export function getTracer() {
  try {
    // Access the tracer from the SplunkRum provider
    const provider = SplunkRum.provider;
    if (provider) {
      return provider.getTracer('appModuleLoader');
    }
    return null;
  } catch (error) {
    console.warn('Failed to get tracer:', error);
    return null;
  }
}

/**
 * Create and track a workflow span
 * Usage:
 *   const span = await createWorkflowSpan('AddToCart', { 'product.id': '123' });
 *   // ... do work ...
 *   span?.end();
 */
export async function createWorkflowSpan(
  workflowName: string,
  attributes: Record<string, string | number> = {}
) {
  const tracer = getTracer();
  if (!tracer) {
    console.warn(`Tracer not available for workflow: ${workflowName}`);
    return null;
  }

  try {
    const span = tracer.startSpan(workflowName, {
      attributes: {
        'workflow.name': workflowName,
        ...attributes,
      },
    });
    return span;
  } catch (error) {
    console.error(`Failed to create workflow span for ${workflowName}:`, error);
    return null;
  }
}

/**
 * Execute a function within a workflow span
 * The span is automatically ended when the function completes or errors
 *
 * Usage:
 *   await executeWithWorkflowSpan('AddToCart', { 'product.id': '123' }, async () => {
 *     await addItemToCart(item);
 *   });
 *
 * With result attributes:
 *   await executeWithWorkflowSpan(
 *     'PlaceOrder',
 *     { 'workflow.name': 'PlaceOrder' },
 *     async () => placeOrderAPI(),
 *     (result, span) => {
 *       span.setAttribute('order.id', result.orderId);
 *     }
 *   );
 */
export async function executeWithWorkflowSpan<T>(
  workflowName: string,
  attributes: Record<string, string | number>,
  fn: () => Promise<T>,
  onResult?: (result: T, span: any) => void
): Promise<T> {
  const span = await createWorkflowSpan(workflowName, attributes);

  try {
    const result = await fn();

    // Allow caller to add result-specific attributes to the span
    if (span && onResult) {
      onResult(result, span);
    }

    return result;
  } catch (error) {
    if (span) {
      // Record the exception on the span
      span.recordException(error as Error);
      span.setStatus({ code: 2, message: (error as Error).message });
    }
    throw error;
  } finally {
    if (span) {
      span.end();

      // Force flush to ensure span is exported to native SDK immediately
      // Fire and forget - don't await to avoid blocking the return
      const provider = SplunkRum.provider;
      if (provider) {
        provider.forceFlush().catch((error) => {
          console.warn('Failed to flush span:', error);
        });
      }
    }
  }
}

/**
 * Create a synthetic error span for testing/demo purposes
 * Similar to the CartPageError in the frontend
 *
 * Usage:
 *   createSyntheticError('CartLoadError', new Error('Failed to load cart'));
 */
export function createSyntheticError(
  errorName: string,
  error: Error,
  attributes: Record<string, string | number | boolean> = {}
) {
  const tracer = getTracer();
  if (!tracer) {
    console.warn(`Tracer not available for error: ${errorName}`);
    return;
  }

  try {
    const span = tracer.startSpan(errorName, {
      attributes: {
        'workflow.name': errorName,
        'error': true,
        'error.synthetic': true,
        ...attributes,
      },
    });

    span.recordException(error);
    span.setStatus({ code: 2, message: error.message });
    span.end();

    console.error(`${errorName}:`, error.message);
  } catch (e) {
    console.error(`Failed to create synthetic error span for ${errorName}:`, e);
  }
}

/**
 * Add an event to the current active span
 *
 * Usage:
 *   addSpanEvent('ProductViewed', { 'product.id': '123', 'product.name': 'Telescope' });
 */
export function addSpanEvent(
  eventName: string,
  attributes: Record<string, string | number> = {}
) {
  const tracer = getTracer();
  if (!tracer) {
    console.warn(`Tracer not available for event: ${eventName}`);
    return;
  }

  try {
    // Get the active span from the tracer context
    const span = tracer.startSpan(eventName);
    span.addEvent(eventName, attributes);
    span.end();
  } catch (error) {
    console.error(`Failed to add event ${eventName}:`, error);
  }
}

/**
 * Update global attributes dynamically
 * Useful for updating user context during the session
 *
 * Usage:
 *   updateGlobalAttributes({ 'enduser.id': '12345', 'enduser.role': 'Member' });
 */
export function updateGlobalAttributes(
  attributes: Record<string, string | number>
) {
  try {
    if (SplunkRum && typeof SplunkRum.setGlobalAttributes === 'function') {
      SplunkRum.setGlobalAttributes(attributes);
      console.log('Updated global RUM attributes:', attributes);
    } else {
      console.warn('setGlobalAttributes not available on SplunkRum');
    }
  } catch (error) {
    console.error('Failed to update global attributes:', error);
  }
}
