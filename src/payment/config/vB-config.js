/**
 * Payment Service Version B Configuration
 * Canary/Error Testing version - Always fails with controlled timing
 */

module.exports = {
  name: 'payment-vB',
  version: 'vB',
  displayVersion: '1.7.0-b',

  // API Configuration
  defaultTokenPrefix: 'prod-vB',
  defaultToken: 'prod-vB-3f2e4d9c-8b7a-4c3d-9e2f-1a4b5c6d7e8f',

  // Version behavior
  alwaysFail: true,  // Version B: Always fails (error testing pod)

  // Retry Configuration
  retryMaxDefault: 4,  // Always 4 attempts
  retryBaseDelayMs: 50,
  retryStrategy: 'random-controlled',  // Special strategy for version B

  // Timing Configuration for Version B (Controlled Failure)
  // Constraints:
  // - Total duration: 4-10 seconds
  // - 3 attempts: 4-7.3 seconds
  // - Each attempt: random duration
  successDelayRange: [0, 100],    // Not used (version B always fails)
  failureDelayRange: [0, 500],    // Not used (using controlled timing instead)

  // Version B specific: Controlled failure timing
  failureTimingConstraints: {
    totalMinMs: 4000,      // Minimum total duration: 4 seconds
    totalMaxMs: 10000,     // Maximum total duration: 10 seconds
    threeAttemptsMinMs: 4000,   // 3 attempts: minimum 4 seconds
    threeAttemptsMaxMs: 7300,   // 3 attempts: maximum 7.3 seconds
  },

  // Timeouts
  requestTimeoutMs: 15000,  // Higher timeout to accommodate delays

  // Feature Flags
  useRetryMaxFlag: false,  // Version B always uses 4 retries
  usePaymentFailureFlag: false,  // Routing handled by checkout

  // Logging (verbose for error analysis)
  logLevel: process.env.LOG_LEVEL || 'debug',

  // OTEL Resource Attributes
  resourceAttributes: {
    'service.version': '1.7.0-b',
    'payment.variant': 'B',
    'payment.api.version': 'v2',
    'deployment.stability': 'canary',
  },

  // Version-specific features
  features: {
    enhancedLogging: true,
    metricsV2: true,
    circuitBreaker: false,  // Disabled for error testing
  },
};
