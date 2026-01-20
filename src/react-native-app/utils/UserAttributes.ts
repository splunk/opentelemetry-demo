// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Splunk RUM User Attributes Generator for React Native
 * Generates deterministic user attributes based on session ID
 * Ported from the frontend implementation
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

interface User {
  id: string;
  role: 'Admin' | 'Member' | 'Guest';
}

interface Session {
  userId: string;
  currencyCode: string;
  timestamp: number;
}

interface GlobalAttributes {
  'enduser.id': string;
  'enduser.role': string;
  'deployment.type': string;
  [key: string]: string | number | boolean | undefined;
}

// Session timeout: 30 minutes
const SESSION_TIMEOUT = 30 * 60 * 1000;
const SESSION_KEY = '@astronomy_shop:session';

// Simple hash function for session ID
function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

// Seeded random number generator
class SeededRandom {
  private seed: number;

  constructor(seed: number) {
    this.seed = seed;
  }

  random(): number {
    const a = 1664525;
    const c = 1013904223;
    const m = Math.pow(2, 32);
    this.seed = (a * this.seed + c) % m;
    return this.seed / m;
  }

  randomInt(min: number, max: number): number {
    return Math.floor(this.random() * (max - min + 1)) + min;
  }
}

// Generate user based on session ID
function randomUser(sessionID: string): User {
  const hash = simpleHash(sessionID);
  const rng = new SeededRandom(hash);
  const r = rng.random();

  let user: User;
  if (r < 0.08) {
    // 8% Admin users
    const adminIDs = [34, 37, 41];
    const adminIndex = rng.randomInt(0, adminIDs.length - 1);
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
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Get or create session ID from AsyncStorage with 30-minute expiration
export async function getSessionId(): Promise<string> {
  try {
    const now = Date.now();
    const sessionStr = await AsyncStorage.getItem(SESSION_KEY);

    if (sessionStr) {
      const session: Session = JSON.parse(sessionStr);
      const sessionAge = now - (session.timestamp || 0);

      // Check if session is expired (older than 30 minutes)
      if (session.timestamp && sessionAge < SESSION_TIMEOUT) {
        console.log('Using existing session:', session.userId);
        return session.userId;
      } else {
        console.log('Session expired, creating new session');
      }
    }

    // Create new session if it doesn't exist or is expired
    const newUserId = generateUUID();
    const newSession: Session = {
      userId: newUserId,
      currencyCode: 'USD',
      timestamp: now
    };
    await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(newSession));
    console.log('New session created with 30-minute expiration:', newUserId);
    return newUserId;
  } catch (e) {
    console.error('Error getting/creating session:', e);
    // Return a fallback UUID if AsyncStorage fails
    return generateUUID();
  }
}

// Reset session (useful for testing or manual reset)
export async function resetSession(): Promise<void> {
  try {
    await AsyncStorage.removeItem(SESSION_KEY);
    console.log('Session reset');
  } catch (e) {
    console.error('Error resetting session:', e);
  }
}

// Main function to generate Splunk RUM global attributes
export async function getSplunkGlobalAttributes(deploymentType: string = 'green'): Promise<GlobalAttributes> {
  // Get session ID and generate user attributes
  const sessionId = await getSessionId();
  console.log('Session ID for RUM:', sessionId);

  const user = randomUser(sessionId);

  const attributes: GlobalAttributes = {
    'enduser.id': user.id,
    'enduser.role': user.role,
    'deployment.type': deploymentType
  };

  console.log('Generated Splunk RUM User Attributes:', attributes);
  return attributes;
}
