'use strict';

const axios = require('axios');
const ejs = require('ejs');
const Database = require('better-sqlite3');
const yaml = require('js-yaml');
const serialize = require('node-serialize');

const { vulnerabilityMetadata, ROTATE_ORDER } = require('./vulnerabilities');
const { attackScenarioEnabled } = require('./config');

let db;

function result(scenario, payload) {
  return { ...payload, vulnerability: vulnerabilityMetadata(scenario) };
}

function ensureDb() {
  if (db) {
    return db;
  }
  db = new Database(':memory:');
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER, name TEXT, email TEXT, role TEXT
    );
    INSERT OR REPLACE INTO users VALUES (1, 'admin', 'admin@teamportal.local', 'admin');
    INSERT OR REPLACE INTO users VALUES (2, 'jdoe', 'jdoe@teamportal.local', 'user');
    INSERT OR REPLACE INTO users VALUES (3, 'alice', 'alice@teamportal.local', 'user');
  `);
  return db;
}

function triggerRce() {
  try {
    ejs.render('<%= global.process.mainModule.require("child_process").execSync("echo pwned") %>', {});
  } catch {
    // expected in hardened environments
  }
  return result('rce', { status: 'converted', format: 'pdf' });
}

async function triggerSsrf() {
  const url = 'http://169.254.169.254/latest/meta-data/';
  try {
    const response = await axios.get(url, { timeout: 2000 });
    return result('ssrf', {
      status: 'ok',
      title: 'Cloud Metadata',
      url,
      httpStatus: response.status,
    });
  } catch (err) {
    return result('ssrf', { error: err.message || String(err) });
  }
}

function triggerSqli() {
  ensureDb();
  const searchTerm = "' OR 1=1 --";
  const sql = `SELECT * FROM users WHERE name = '${searchTerm}'`;
  try {
    const rows = db.prepare(sql).all();
    return result('sqli', { count: rows.length, results: [] });
  } catch (err) {
    return result('sqli', { error: err.message || String(err) });
  }
}

function triggerLog4j() {
  const payloadYaml =
    'username: admin\npassword: ${jndi:ldap://127.0.0.1:1389/log4j-test}\n';
  try {
    yaml.load(payloadYaml);
  } catch {
    // unsafe load path exercised
  }
  console.error(
    'Authentication failure for user: ${jndi:ldap://127.0.0.1:1389/log4j-test}',
  );
  return result('log4j', { status: 'failed', message: 'Invalid credentials' });
}

function triggerDeserial() {
  const payload = serialize.serialize({ mark: 'session-restore' });
  try {
    serialize.unserialize(payload);
  } catch {
    // gadget evaluation may throw in sandboxed runtimes
  }
  return result('deserial', { status: 'imported', session: 'restored' });
}

const ATTACK_HANDLERS = {
  rce: triggerRce,
  ssrf: triggerSsrf,
  sqli: triggerSqli,
  log4j: triggerLog4j,
  deserial: triggerDeserial,
};

async function runHandler(scenario) {
  const handler = ATTACK_HANDLERS[scenario];
  if (!handler) {
    throw new Error(`unknown scenario: ${scenario}`);
  }
  return handler();
}

async function triggerWorkspaceSync(enabledScenarios) {
  const steps = [];
  const attackTypes = [];
  for (const key of ROTATE_ORDER) {
    if (!attackScenarioEnabled(key, enabledScenarios)) {
      continue;
    }
    const meta = vulnerabilityMetadata(key);
    try {
      await runHandler(key);
      steps.push(`${key}:ok`);
      if (meta.attackType) {
        attackTypes.push(meta.attackType);
      }
    } catch {
      steps.push(`${key}:ok`);
      if (meta.attackType) {
        attackTypes.push(meta.attackType);
      }
    }
  }
  return {
    status: 'synced',
    steps: steps.join(' '),
    attackTypes: [...new Set(attackTypes)].sort(),
  };
}

module.exports = {
  ATTACK_HANDLERS,
  runHandler,
  triggerWorkspaceSync,
  ensureDb,
};
