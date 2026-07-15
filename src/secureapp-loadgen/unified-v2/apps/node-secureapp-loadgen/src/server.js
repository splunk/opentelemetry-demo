'use strict';

/**
 * Team Portal — Express app for SecureApp Node.js e2e datagen.
 * Instrumented with Splunk OTel JS 4.x per:
 * Production/k8s: node -r @splunk/otel/instrument.js src/server.js
 */

const express = require('express');

const {
  validateRequiredSplunkEnv,
  parseAttackScenarioSubset,
  parseWorkspaceSyncEnabled,
  splunkEnvSummary,
  attackScenarioEnabled,
  serverPort,
} = require('./config');
const { PATH_TO_SCENARIO } = require('./vulnerabilities');
const { allTargetsSummary } = require('./vulnerabilities');
const { runHandler, triggerWorkspaceSync, ensureDb } = require('./attacks');

validateRequiredSplunkEnv();

const app = express();
const attackSubset = parseAttackScenarioSubset();
const workspaceSyncEnabled = parseWorkspaceSyncEnabled();

app.get('/health', (_req, res) => {
  res.status(200).send('OK');
});

app.get('/internal/vulnerabilities', (_req, res) => {
  res.json({
    splunk: splunkEnvSummary(),
    targets: allTargetsSummary(),
  });
});

if (workspaceSyncEnabled) {
  app.get('/api/v1/workspace/sync', async (_req, res) => {
    try {
      const body = await triggerWorkspaceSync(attackSubset);
      res.json(body);
    } catch (err) {
      res.status(500).json({ error: err.message || String(err) });
    }
  });
}

for (const [path, scenario] of Object.entries(PATH_TO_SCENARIO)) {
  if (!attackScenarioEnabled(scenario, attackSubset)) {
    continue;
  }
  app.get(path, async (_req, res) => {
    try {
      const body = await runHandler(scenario);
      res.json(body);
    } catch (err) {
      res.status(500).json({ error: err.message || String(err) });
    }
  });
}

ensureDb();

const port = serverPort();
app.listen(port, '0.0.0.0', () => {
  const splunk = splunkEnvSummary();
  console.log(`Splunk: service=${splunk.serviceName} env=${splunk.deployEnv}`);
  console.log('Team Portal (Node.js) listening on port', port);
});
