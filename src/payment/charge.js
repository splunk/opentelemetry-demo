// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
const { context, propagation, trace, metrics, SpanKind, SpanStatusCode } = require('@opentelemetry/api');
const cardValidator = require('simple-card-validator');
const { v4: uuidv4 } = require('uuid');

const { OpenFeature } = require('@openfeature/server-sdk');
const { FlagdProvider } = require('@openfeature/flagd-provider');
const flagProvider = new FlagdProvider();

const logger = require('./logger');

// Load version-specific configuration
const versionConfig = require('./config/version-config');

// Initialize tracer with version info
const tracer = trace.getTracer('payment', versionConfig.displayVersion);
const meter = metrics.getMeter('payment', versionConfig.displayVersion);
const transactionsCounter = meter.createCounter('app.payment.transactions');

// Log which version is running
logger.info({
  version: versionConfig.version,
  displayVersion: versionConfig.displayVersion,
  name: versionConfig.name,
  apiToken: versionConfig.apiToken.substring(0, 20) + '...',
  retryMaxDefault: versionConfig.retryMaxDefault,
  retryStrategy: versionConfig.retryStrategy,
}, `Payment service ${versionConfig.displayVersion} initialized`);

const LOYALTY_LEVEL = ['platinum', 'gold', 'silver', 'bronze'];

// External service simulation - now uses version config
const SUCCESS_VERSION = versionConfig.displayVersion;
const FAILURE_VERSION = versionConfig.displayVersion.replace(/(\d+)$/, (match) => `${parseInt(match) + 1}`);
const API_TOKEN_SUCCESS_TOKEN = versionConfig.apiToken;
const API_TOKEN_FAILURE_TOKEN = versionConfig.apiToken.replace('prod', 'test');
// Version-specific timing from config
const SUCCESS_PAYMENT_SERVICE_DURATION_MILLIS = versionConfig.successDelayRange[1];
const ERROR_PAYMENT_SERVICE_DURATION_MILLIS = versionConfig.failureDelayRange[1];

function random(arr) {
  const index = Math.floor(Math.random() * arr.length);
  return arr[index];
}

function randomInt(from, to) {
  return Math.floor((to - from) * Math.random() + from);
}

// Error types compatible with original behavior
class InvalidRequestError extends Error {
  constructor() {
    super('Invalid request');
    this.code = 401; // Authorization error
  }
}

class CreditCardError extends Error {
  constructor(message) {
    super(message);
    this.code = 400; // Invalid argument error
  }
}

class InvalidCreditCard extends CreditCardError {
  constructor() {
    super('Credit card info is invalid.');
  }
}

class UnacceptedCreditCard extends CreditCardError {
  constructor(cardType) {
    super(`Sorry, we cannot process ${cardType} credit cards. Only VISA or MasterCard is accepted.`);
  }
}

class ExpiredCreditCard extends CreditCardError {
  constructor(number, month, year) {
    super(`The credit card (ending ${number.substr(-4)}) expired on ${month}/${year}.`);
  }
}

// Simulated external payment processor (accepts both new and original request shapes)
function buttercupPaymentsApiCharge(request, token, customDelayMs = null) {
  return new Promise((resolve, reject) => {
    if (token === API_TOKEN_FAILURE_TOKEN) {
      const timeoutMillis = customDelayMs !== null ? customDelayMs : randomInt(0, ERROR_PAYMENT_SERVICE_DURATION_MILLIS);
      setTimeout(() => reject(new InvalidRequestError()), timeoutMillis);
      return;
    }

    // Normalize request shape
    const amount = request.amount || request.Amount || {};
    const creditCard = request.creditCard || request.credit_card || {};
    const cardNumber = creditCard.creditCardNumber || creditCard.number || creditCard.credit_card_number;
    const year = creditCard.creditCardExpirationYear || creditCard.year || creditCard.credit_card_expiration_year;
    const month = creditCard.creditCardExpirationMonth || creditCard.month || creditCard.credit_card_expiration_month;

    const cardInfo = cardValidator(cardNumber);
    const { card_type: cardType, valid } = cardInfo.getCardDetails();

    if (!valid) {
      reject(new InvalidCreditCard());
      return;
    }

    if (!(cardType === 'visa' || cardType === 'mastercard')) {
      reject(new UnacceptedCreditCard(cardType));
      return;
    }

    const currentMonth = new Date().getMonth() + 1;
    const currentYear = new Date().getFullYear();
    if (currentYear * 12 + currentMonth > year * 12 + month) {
      reject(new ExpiredCreditCard(String(cardNumber).replace('-', ''), month, year));
      return;
    }

    // Use version-specific success delay range
    const timeoutMillis = randomInt(versionConfig.successDelayRange[0], versionConfig.successDelayRange[1]);
    setTimeout(() => {
      resolve({
        transaction_id: uuidv4(),
        cardType,
        cardNumber,
        amount: {
          currency_code: amount.currencyCode || amount.currency_code,
          units: amount.units,
          nanos: amount.nanos,
        },
      });
    }, timeoutMillis);
  });
}

// Helper function to distribute delay across retry attempts
// Version A: Not used (succeeds immediately)
// Version B: Controlled timing with constraints:
//   - Total: 4-10 seconds
//   - 3 attempts: 4-7.3 seconds
//   - Each attempt: random duration
function calculateFailureTimings(totalAttempts) {
  // Version B specific: Use controlled timing constraints
  if (versionConfig.alwaysFail && versionConfig.failureTimingConstraints) {
    const constraints = versionConfig.failureTimingConstraints;

    // Randomly decide total duration (4-10 seconds)
    const totalDurationMs = randomInt(constraints.totalMinMs, constraints.totalMaxMs);

    // Calculate duration for first 3 attempts (4-7.3 seconds)
    const threeAttemptsDuration = randomInt(
      constraints.threeAttemptsMinMs,
      Math.min(constraints.threeAttemptsMaxMs, totalDurationMs - 500)  // Leave at least 500ms for 4th attempt
    );

    // Duration for 4th attempt (remaining time)
    const fourthAttemptDuration = totalDurationMs - threeAttemptsDuration;

    // Distribute time across first 3 attempts randomly
    const timings = [];
    let remainingThreeAttemptsTime = threeAttemptsDuration;

    for (let i = 0; i < 3; i++) {
      // Random distribution for first 2 attempts, remainder for 3rd
      let attemptTime;
      if (i < 2) {
        // Random portion of remaining time (between 20% and 50%)
        const minPortion = 0.2;
        const maxPortion = 0.5;
        const portion = minPortion + Math.random() * (maxPortion - minPortion);
        attemptTime = Math.floor(remainingThreeAttemptsTime * portion);
      } else {
        // 3rd attempt gets the remainder
        attemptTime = remainingThreeAttemptsTime;
      }

      // Split between API delay and backoff (70/30)
      const apiDelay = Math.floor(attemptTime * 0.7);
      const backoff = attemptTime - apiDelay;

      timings.push({ apiDelay, backoff });
      remainingThreeAttemptsTime -= attemptTime;
    }

    // 4th attempt (final, no backoff)
    timings.push({
      apiDelay: fourthAttemptDuration,
      backoff: 0
    });

    logger.info({
      totalDurationMs,
      threeAttemptsDuration,
      fourthAttemptDuration,
      timings,
      version: versionConfig.version
    }, 'Version B: Calculated controlled failure timings');

    return { timings, totalDurationMs };
  }

  // Fallback for version A or if constraints not defined (shouldn't be used)
  const baseTarget = versionConfig.totalFailureTargetMs || 5000;
  const totalDurationMs = randomInt(baseTarget, baseTarget + 1000);

  const timings = [];
  let remainingTime = totalDurationMs;

  for (let i = 0; i < totalAttempts; i++) {
    const isLastAttempt = i === totalAttempts - 1;

    const weight = Math.pow(1.5, i);
    const totalWeight = Array.from({length: totalAttempts}, (_, idx) => Math.pow(1.5, idx))
      .reduce((sum, w) => sum + w, 0);

    let attemptTime = Math.floor((weight / totalWeight) * totalDurationMs);

    if (isLastAttempt) {
      attemptTime = remainingTime;
    }

    let apiDelay, backoff;
    if (isLastAttempt) {
      apiDelay = attemptTime;
      backoff = 0;
    } else {
      apiDelay = Math.floor(attemptTime * 0.7);
      backoff = attemptTime - apiDelay;
    }

    timings.push({ apiDelay, backoff });
    remainingTime -= attemptTime;
  }

  return { timings, totalDurationMs };
}

module.exports.charge = async request => {
  // Create a SERVER span so attributes are promoted in Splunk O11y
  const span = tracer.startSpan('charge', {
    kind: SpanKind.SERVER,
    attributes: {
      'rpc.system': 'grpc',
      'rpc.service': 'PaymentService',
      'rpc.method': 'Charge',
      // Add version-specific attributes
      ...versionConfig.resourceAttributes,
    }
  });
  await OpenFeature.setProviderAndWait(flagProvider);

  // Use version-specific retry settings with optional feature flag override
  let RETRY_MAX = versionConfig.retryMaxDefault;
  if (versionConfig.useRetryMaxFlag) {
    try {
      const retryMaxRaw = await OpenFeature.getClient().getNumberValue('paymentRetryMax', versionConfig.retryMaxDefault);
      RETRY_MAX = Math.max(0, Math.floor(retryMaxRaw));
    } catch (e) {
      logger.warn({ error: e.message }, 'Failed to read paymentRetryMax flag, using version default');
    }
  }
  const RETRY_BASE_DELAY_MS = versionConfig.retryBaseDelayMs;

  // Version-specific behavior:
  // - Version A: Normal operation (succeeds)
  // - Version B: Always fails (error testing pod)
  const shouldFailRequest = versionConfig.alwaysFail || false;

  // If this request is destined to fail, pre-calculate timing to ensure 4-8 seconds total
  let failureTimings = null;
  if (shouldFailRequest) {
    failureTimings = calculateFailureTimings(RETRY_MAX);
    logger.info({
      shouldFailRequest: true,
      targetDurationMs: failureTimings.totalDurationMs,
      timings: failureTimings.timings
    }, 'Request will fail - calculated failure timings');
  }

  const creditCard = request.creditCard || request.credit_card || {};
  const card = cardValidator(creditCard.creditCardNumber || creditCard.number || creditCard.credit_card_number);
  const { card_type: cardType, valid } = card.getCardDetails();
  const loyalty_level = random(LOYALTY_LEVEL);
  // Default to success version; on ultimate failure we overwrite to FAILURE_VERSION below
  const version = SUCCESS_VERSION;

  span.setAttributes({
    version,
    'app.payment.card_type': cardType,
    'app.payment.card_valid': valid,
    'app.loyalty.level': loyalty_level,
  });

  // Add planned failure information to span
  if (shouldFailRequest && failureTimings) {
    span.setAttributes({
      'app.payment.planned_failure': true,
      'app.payment.target_duration_ms': failureTimings.totalDurationMs
    });
  }

  let attempt = 0;
  let lastErr = null;

  function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  try {
    let result = null;
    for (attempt = 1; attempt <= RETRY_MAX; attempt++) {
      // Create a new client span per attempt
      const clientSpan = tracer.startSpan(
        'buttercup.payments.api',
        {
          kind: SpanKind.CLIENT,
          attributes: {
            'peer.service': 'ButtercupPayments',
            'http.url': 'https://api.buttercup-payments.com/charge',
            'http.method': 'POST',
            'net.peer.name': 'api.buttercup-payments.com',
            'net.peer.port': 443,
            'retry.attempt': attempt,
          },
        },
        trace.setSpan(context.active(), span)
      );

      // Use the pre-determined success/failure decision (made once per request)
      const token = shouldFailRequest ? API_TOKEN_FAILURE_TOKEN : API_TOKEN_SUCCESS_TOKEN;

      // Get pre-calculated timing for this attempt (if failing)
      const attemptTiming = failureTimings ? failureTimings.timings[attempt - 1] : null;
      const customApiDelay = attemptTiming ? attemptTiming.apiDelay : null;

      clientSpan.addEvent('attempt.start', {
        attempt,
        shouldFailRequest,
        customApiDelay,
        plannedBackoff: attemptTiming ? attemptTiming.backoff : null
      });
      try {
        const resp = await buttercupPaymentsApiCharge(request, token, customApiDelay);
        // Success
        clientSpan.addEvent('attempt.success', { attempt });
        clientSpan.setAttributes({ 'http.status_code': '200' });
        span.setStatus({ code: SpanStatusCode.OK });
        // Log within the OTel context of the client span before ending it
        context.with(trace.setSpan(context.active(), clientSpan), () => {
          logger.info(
            {
              severity: 'info',
              time: Math.floor(Date.now() / 1000),
              pid: process.pid,
              hostname: require('os').hostname(),
              name: 'paymentservice',
              trace_id: trace.getSpan(context.active()).spanContext().traceId,
              span_id: trace.getSpan(context.active()).spanContext().spanId,
              'service.name': 'payment',
              token: token,
              version: SUCCESS_VERSION,
              message: 'Charging through ButtercupPayments',
            }
          );
        });
        clientSpan.end();

        const baggage = propagation.getBaggage(context.active());
        const synthetic = baggage && baggage.getEntry('synthetic_request') && baggage.getEntry('synthetic_request').value === 'true';

        if (synthetic) {
          logger.info(
            {
              severity: 'info',
              time: Math.floor(Date.now() / 1000),
              pid: process.pid,
              hostname: require('os').hostname(),
              name: 'payment',
              trace_id: trace.getSpan(context.active()).spanContext().traceId,
              span_id: trace.getSpan(context.active()).spanContext().spanId,
              'service.name': 'payment',
              message: 'Processing synthetic request - setting app.payment.charged=false',
              synthetic_request: true,
            }
          );
        }

        span.setAttribute('app.payment.charged', !synthetic);

        const { transaction_id, cardType: resolvedCardType, cardNumber, amount } = resp;

        logger.info(
          {
            transactionId: transaction_id,
            cardType: resolvedCardType,
            lastFourDigits: String(cardNumber).substr(-4),
            amount: {
              units: amount.units,
              nanos: amount.nanos,
              currencyCode: amount.currency_code,
            },
            loyalty_level,
            retry_count: attempt - 1,
          },
          'Transaction complete.'
        );
        transactionsCounter.add(1, { 'app.payment.currency': amount.currency_code });
        span.setAttributes({ 'retry.count': attempt - 1, 'retry.success': true });
        result = { transactionId: transaction_id, success: true, retries: attempt - 1 };
        break;

      } catch (err) {
        lastErr = err;
        clientSpan.addEvent('attempt.failure', { attempt, code: String(err.code || 401) });
        clientSpan.setAttributes({ 'http.status_code': String(err.code || 401) });


        // Flag the root span for every 401 attempt (not just the final failure)
        if (err.code === 401) {
          span.setAttributes({
            version: FAILURE_VERSION,
            // TODO: populate actual kubernetes_pod_uid via Downward API (e.g., env var K8S_POD_UID)
            //kubernetes_pod_uid: process.env.K8S_POD_UID || 'UNKNOWN',
            error: true,
          });
        }

        // TODO: Revisit this log message to adjust for non-401 errors (currently always logs "Invalid API Token")
        // Per-attempt failure log in original raw JSON shape (keep version; lowercase severity)
        // Log within the OTel context of the client span before ending it
        context.with(trace.setSpan(context.active(), clientSpan), () => {
          logger.error(
            {
              severity: 'error',
              time: Math.floor(Date.now() / 1000),
              pid: process.pid,
              hostname: require('os').hostname(),
              name: 'payment',
              trace_id: trace.getSpan(context.active()).spanContext().traceId,
              span_id: trace.getSpan(context.active()).spanContext().spanId,
              'service.name': 'payment',
              token: API_TOKEN_FAILURE_TOKEN,
              version: FAILURE_VERSION,
              message: `Failed payment processing through ButtercupPayments: Invalid API Token (${API_TOKEN_FAILURE_TOKEN})`,
            }
          );
        });
        clientSpan.end();

        // If more attempts remain, backoff and retry
        if (attempt < RETRY_MAX) {
          // Use pre-calculated backoff if this is a planned failure
          let delay;
          if (attemptTiming) {
            delay = attemptTiming.backoff;
          } else {
            // Use version-specific retry strategy
            delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
            // Add jitter if using exponential-jitter strategy
            if (versionConfig.retryStrategy === 'exponential-jitter' && versionConfig.jitterMaxMs) {
              const jitter = Math.random() * versionConfig.jitterMaxMs;
              delay += jitter;
            }
          }
          await sleep(delay);
          continue;
        }
      }
    }

    if (result) {
      return result;
    }

// All attempts failed: mark spans and return a 500/401-style failure (no throw)
    const finalCode = (lastErr && lastErr.code === 401) ? 401 : 500;

    span.setAttributes({
      version: FAILURE_VERSION,
      error: true,
      'app.loyalty.level': 'gold',
      'retry.count': attempt - 1,
      'retry.success': false,
      'http.status_code': finalCode,
    });

    // set explicit error status on the root span so it doesn't show as "unknown"
    span.setStatus({ code: SpanStatusCode.ERROR, message: String(finalCode) });

    // keep baggage handling as you have it
    const baggage = propagation.getBaggage(context.active());
    const synthetic = baggage && baggage.getEntry('synthetic_request') && baggage.getEntry('synthetic_request').value === 'true';

    if (synthetic) {
      logger.info(
        {
          severity: 'info',
          time: Math.floor(Date.now() / 1000),
          pid: process.pid,
          hostname: require('os').hostname(),
          name: 'payment',
          trace_id: trace.getSpan(context.active()).spanContext().traceId,
          span_id: trace.getSpan(context.active()).spanContext().spanId,
          'service.name': 'payment',
          message: 'Processing synthetic request (all retries failed) - setting app.payment.charged=false',
          synthetic_request: true,
        }
      );
    }

    span.setAttribute('app.payment.charged', false);

    // final log INSIDE the root span context (so trace/span ids are injected)
    context.with(trace.setSpan(context.active(), span), () => {
      if (finalCode === 401) {
        logger.error(
          {
            severity: 'error',
            time: Math.floor(Date.now() / 1000),
            pid: process.pid,
            hostname: require('os').hostname(),
            name: 'paymentservice',
            trace_id: trace.getSpan(context.active()).spanContext().traceId,
            span_id: trace.getSpan(context.active()).spanContext().spanId,
            'service.name': 'paymentservice',
            token: API_TOKEN_FAILURE_TOKEN,
            version: FAILURE_VERSION,
            message: `Failed payment processing through ButtercupPayments after ${RETRY_MAX} retries: Invalid API Token (${API_TOKEN_FAILURE_TOKEN})`,

          }
        );
      } else {
        logger.error(
          {
            severity: 'error',
            time: Math.floor(Date.now() / 1000),
            pid: process.pid,
            hostname: require('os').hostname(),
            name: 'paymentservice',
            trace_id: trace.getSpan(context.active()).spanContext().traceId,
            span_id: trace.getSpan(context.active()).spanContext().spanId,
            'service.name': 'paymentservice',
            version: FAILURE_VERSION,
            message: 'Failed payment processing through ButtercupPayments after retries',

          }
        );
      }
    });
    // Throw after all retries so upstream services see the failure
    const errToThrow = new Error(
      finalCode === 401
        ? `Payment failed after retries: Invalid API Token (${API_TOKEN_FAILURE_TOKEN})`
        : 'Payment failed after retries'
    );
    // attach code for structured error handling
    errToThrow.code = finalCode;
throw errToThrow;
  } finally {
    span.end();
  }
};
