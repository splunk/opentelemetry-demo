// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Splunk RUM User Attributes Generator
 * This script generates deterministic user attributes based on session ID
 * Ported from the original Go implementation
 *
 * user.deployment_type Behavior:
 * ==============================
 * This attribute controls how payment routing is tracked in RUM.
 *
 * When rumBlueGreen flag is OFF (default):
 *   - Uses DEPLOYMENT_TYPE environment variable if set (e.g., 'blue', 'canary')
 *   - Falls back to 'green' as the default value
 *   - Change DEPLOYMENT_TYPE env var on the fly to update all new sessions
 *   - Checkout service makes its own payment routing decision using paymentFailure flag
 *
 * When rumBlueGreen flag is ON:
 *   - Default payment path is 'payment-a' (routes to stable payment service)
 *   - Clicking logo on homepage resets user AND toggles payment path
 *   - First reset: switches to 'payment-b', second reset: back to 'payment-a', etc.
 *   - Stored in session and passed to checkout service via X-Payment-Path header
 *   - Checkout service honors the header instead of making its own decision
 *   - Enables RUM tracking of payment path throughout entire user journey
 *   - Reset message shows current path (A or B) for visibility
 */

// Simple hash function for session ID
function simpleHash(str) {
  var hash = 0;
  for (var i = 0; i < str.length; i++) {
    var char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

// Seeded random number generator
function SeededRandom(seed) {
  this.seed = seed;
}

SeededRandom.prototype.random = function() {
  var a = 1664525;
  var c = 1013904223;
  var m = Math.pow(2, 32);
  this.seed = (a * this.seed + c) % m;
  return this.seed / m;
};

SeededRandom.prototype.randomInt = function(min, max) {
  return Math.floor(this.random() * (max - min + 1)) + min;
};

// Generate user based on session ID
function randomUser(sessionID) {
  var hash = simpleHash(sessionID);
  var rng = new SeededRandom(hash);
  var r = rng.random();

  var user;
  if (r < 0.08) {
    // 8% Admin users
    var adminIDs = [34, 37, 41];
    var adminIndex = rng.randomInt(0, adminIDs.length - 1);
    user = {
      id: adminIDs[adminIndex].toString(),
      role: 'Admin'
    };
  } else if (r < 0.50) {
    // 42% Member users
    user = {
      id: rng.randomInt(1000, 6000).toString(),
      role: 'Member'
    };
  } else {
    // 50% Guest users
    user = {
      id: '99999',
      role: 'Guest'
    };
  }

  console.log('Generated user from session ID:', sessionID, '-> User ID:', user.id, 'Role:', user.role);
  return user;
}

// Generate a UUID v4
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0;
    var v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Get or create session ID from localStorage with 30-minute expiration
function getSessionId() {
  try {
    var SESSION_TIMEOUT = 30 * 60 * 1000; // 30 minutes in milliseconds
    var now = Date.now();
    var session = localStorage.getItem('session');

    if (session) {
      var sessionObj = JSON.parse(session);
      var sessionAge = now - (sessionObj.timestamp || 0);

      // Check if session is expired (older than 30 minutes)
      if (sessionObj.timestamp && sessionAge < SESSION_TIMEOUT) {
        return sessionObj.userId;
      } else {
        console.log('Session expired or invalid, creating new session');
      }
    }

    // Create new session if it doesn't exist or is expired
    var newUserId = generateUUID();
    var newSession = {
      userId: newUserId,
      currencyCode: 'USD',
      timestamp: now
    };
    localStorage.setItem('session', JSON.stringify(newSession));
    console.log('New session created with 30-minute expiration');
    return newUserId;
  } catch (e) {
    console.error('Error getting/creating session:', e);
    return null;
  }
}

// Fetch flag value from flagd OFREP API
async function getFlagValue(flagName, defaultValue) {
  try {
    var response = await fetch('/flagservice/ofrep/v1/evaluate/flags/' + flagName, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: {} })
    });
    if (!response.ok) {
      console.warn('Flag fetch failed for ' + flagName + ':', response.status);
      return defaultValue;
    }
    var data = await response.json();
    return data.value !== undefined ? data.value : defaultValue;
  } catch (e) {
    console.warn('Failed to fetch ' + flagName + ' flag:', e);
    return defaultValue;
  }
}

// Get default payment path (always starts with payment-a)
function getDefaultPaymentPath() {
  return 'payment-a';
}

// Toggle payment path between A and B
function togglePaymentPath() {
  var currentPath = getStoredPaymentPath() || 'payment-a';
  var newPath = currentPath === 'payment-a' ? 'payment-b' : 'payment-a';
  console.log('Toggling payment path:', currentPath, '->', newPath);
  return newPath;
}

// Store payment path in session for checkout to use
function storePaymentPath(path) {
  try {
    var session = localStorage.getItem('session');
    if (session) {
      var sessionObj = JSON.parse(session);
      sessionObj.paymentPath = path;
      localStorage.setItem('session', JSON.stringify(sessionObj));
    }
  } catch (e) {
    console.warn('Failed to store payment path:', e);
  }
}

// Get stored payment path from session
function getStoredPaymentPath() {
  try {
    var session = localStorage.getItem('session');
    if (session) {
      var sessionObj = JSON.parse(session);
      return sessionObj.paymentPath || null;
    }
  } catch (e) {
    console.warn('Failed to get stored payment path:', e);
  }
  return null;
}

// Initialize payment path based on rumBlueGreen flag (async, called after page load)
async function initPaymentPath() {
  try {
    var rumBlueGreenEnabled = await getFlagValue('rumBlueGreen', false);
    console.log('rumBlueGreen flag:', rumBlueGreenEnabled);

    if (rumBlueGreenEnabled) {
      var storedPath = getStoredPaymentPath();

      // Use stored path if available, otherwise default to payment-a
      if (!storedPath) {
        storedPath = getDefaultPaymentPath();
        storePaymentPath(storedPath);
        console.log('Initialized default payment path:', storedPath);
      }

      // Update RUM with payment path as deployment type
      if (typeof window.SplunkRum !== 'undefined' && window.SplunkRum.setGlobalAttributes) {
        window.SplunkRum.setGlobalAttributes({ 'user.deployment_type': storedPath });
        console.log('Updated RUM deployment_type to:', storedPath);
      }

      return storedPath;
    }
  } catch (e) {
    console.warn('Failed to initialize payment path:', e);
  }
  return null;
}

// Toggle payment path and update RUM (called on user reset when rumBlueGreen is ON)
async function toggleAndStorePaymentPath() {
  try {
    var rumBlueGreenEnabled = await getFlagValue('rumBlueGreen', false);
    if (!rumBlueGreenEnabled) {
      return null;
    }

    var newPath = togglePaymentPath();
    storePaymentPath(newPath);

    // Update RUM with new payment path
    if (typeof window.SplunkRum !== 'undefined' && window.SplunkRum.setGlobalAttributes) {
      window.SplunkRum.setGlobalAttributes({ 'user.deployment_type': newPath });
      console.log('Toggled RUM deployment_type to:', newPath);
    }

    return newPath;
  } catch (e) {
    console.warn('Failed to toggle payment path:', e);
    return null;
  }
}

// Main function to generate Splunk RUM global attributes (synchronous for initial RUM setup)
function getSplunkGlobalAttributes() {
  // Get session ID and generate user attributes
  var sessionId = getSessionId();
  console.log('Session ID for RUM:', sessionId);

  var user = sessionId ? randomUser(sessionId) : { id: '99999', role: 'Guest' };

  // Determine deployment type with fallback chain:
  // 1. Stored payment path (set by initPaymentPath when rumBlueGreen is ON) - 'payment-a' or 'payment-b'
  // 2. DEPLOYMENT_TYPE env var (allows on-the-fly changes when rumBlueGreen is OFF)
  // 3. Default: 'green'
  var storedPath = getStoredPaymentPath();
  var deploymentType = storedPath || window.ENV.DEPLOYMENT_TYPE || 'green';

  var attributes = {
    'user.customer_id': user.id,
    'user.role': user.role,
    'user.deployment_type': deploymentType
  };

  console.log('Generated Splunk RUM User Attributes:', attributes);

  // Async: Initialize payment path after initial load (will update RUM if needed)
  setTimeout(function() {
    initPaymentPath();
  }, 100);

  return attributes;
}
