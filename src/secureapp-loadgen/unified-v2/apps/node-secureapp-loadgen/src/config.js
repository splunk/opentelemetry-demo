'use strict';

/** Environment-driven configuration (Splunk OTel + SecureApp identity). */

function parseAttackScenarioSubset() {
  const raw = (process.env.ATTACK_ENABLED_SCENARIOS || '').trim();
  if (!raw) {
    return null;
  }
  const subset = new Set(
    raw.split(',').map((p) => p.trim().toLowerCase()).filter(Boolean),
  );
  return subset.size ? subset : null;
}

function attackScenarioEnabled(scenarioKey, subset) {
  if (!subset) {
    return true;
  }
  return subset.has(String(scenarioKey).toLowerCase());
}

function parseWorkspaceSyncEnabled() {
  const raw = (process.env.WORKSPACE_SYNC_ENABLED || '').trim().toLowerCase();
  return ['1', 'true', 'yes', 'on'].includes(raw);
}

function resolveServiceName() {
  return (
    (process.env.SERVICE_NAME || '').trim() ||
    (process.env.OTEL_SERVICE_NAME || '').trim()
  );
}

function resolveDeployEnv() {
  const explicit = (process.env.DEPLOY_ENV || '').trim();
  if (explicit) {
    return explicit;
  }
  const attrs = process.env.OTEL_RESOURCE_ATTRIBUTES || '';
  for (const part of attrs.split(',')) {
    const trimmed = part.trim();
    if (trimmed.startsWith('deployment.environment.name=')) {
      return trimmed.split('=').slice(1).join('=').trim();
    }
    if (trimmed.startsWith('deployment.environment=')) {
      return trimmed.split('=').slice(1).join('=').trim();
    }
  }
  return '';
}

function validateRequiredSplunkEnv() {
  const missing = [];
  if (!resolveServiceName()) {
    missing.push('SERVICE_NAME (or OTEL_SERVICE_NAME)');
  }
  if (!resolveDeployEnv()) {
    missing.push(
      'DEPLOY_ENV (or deployment.environment / deployment.environment.name in OTEL_RESOURCE_ATTRIBUTES)',
    );
  }
  if (missing.length) {
    console.error(
      `ERROR: missing required environment variables: ${missing.join(', ')}`,
    );
    process.exit(1);
  }
}

function splunkEnvSummary() {
  return {
    realm: process.env.REALM || '',
    serviceName: resolveServiceName(),
    deployEnv: resolveDeployEnv(),
  };
}

function serverPort() {
  const raw = (process.env.SERVER_PORT || '8080').trim();
  const port = Number.parseInt(raw, 10);
  return Number.isFinite(port) ? port : 8080;
}

module.exports = {
  parseAttackScenarioSubset,
  attackScenarioEnabled,
  parseWorkspaceSyncEnabled,
  validateRequiredSplunkEnv,
  splunkEnvSummary,
  serverPort,
};
