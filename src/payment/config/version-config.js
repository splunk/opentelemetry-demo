/**
 * Version Configuration Loader
 * Loads version-specific config based on PAYMENT_VERSION env var
 */

const fs = require('fs');
const path = require('path');

const vAConfig = require('./vA-config');
const vBConfig = require('./vB-config');

// Read from environment (set at build time or runtime)
const PAYMENT_VERSION = process.env.PAYMENT_VERSION || 'vA';

const versionConfigs = {
  'vA': vAConfig,
  'vB': vBConfig,
};

function loadVersionConfig() {
  const config = versionConfigs[PAYMENT_VERSION];

  if (!config) {
    console.error(`❌ Unknown PAYMENT_VERSION: ${PAYMENT_VERSION}`);
    console.error('   Valid versions: vA, vB');
    console.error('   Defaulting to vA');
    return versionConfigs['vA'];
  }

  console.log(`✅ Loaded payment service configuration for ${PAYMENT_VERSION}`);

  // Read build-time version metadata if available
  try {
    const versionMetadata = fs.readFileSync(
      path.join(__dirname, '../version.json'),
      'utf8'
    );
    const metadata = JSON.parse(versionMetadata);
    console.log('📦 Build metadata:', JSON.stringify(metadata, null, 2));
  } catch (e) {
    // version.json not available (dev mode)
  }

  return config;
}

// Export config and version info
const config = loadVersionConfig();

module.exports = {
  ...config,
  version: PAYMENT_VERSION,
  // Token from secret takes precedence
  apiToken: process.env.PAYMENT_API_TOKEN || config.defaultToken,
};
