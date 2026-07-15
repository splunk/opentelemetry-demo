'use strict';

/** CVE-to-attack mapping for intentionally pinned vulnerable npm packages. */

const VULNERABILITY_TARGETS = {
  rce: {
    scenario: 'rce',
    cveId: 'CVE-2022-29078',
    package: 'ejs',
    pinnedVersion: '2.7.4',
    severity: 'low',
    attackType: 'RCE',
    description: 'EJS server-side template injection via unsafe render',
    requireName: 'ejs',
  },
  ssrf: {
    scenario: 'ssrf',
    cveId: 'CVE-2021-3749',
    package: 'axios',
    pinnedVersion: '0.21.1',
    severity: 'low',
    attackType: 'SSRF',
    description: 'SSRF via axios fetch to cloud metadata endpoint',
    requireName: 'axios',
  },
  sqli: {
    scenario: 'sqli',
    cveId: 'CVE-2022-25897',
    package: 'better-sqlite3',
    pinnedVersion: '11.7.0',
    severity: 'low',
    attackType: 'SQL',
    description: 'SQL injection via concatenated better-sqlite3 query',
    requireName: 'better-sqlite3',
  },
  log4j: {
    scenario: 'log4j',
    cveId: 'CVE-2020-14343',
    package: 'js-yaml',
    pinnedVersion: '3.13.1',
    severity: 'low',
    attackType: 'LOG4J',
    description: 'Unsafe js-yaml load of JNDI-style credential payload (Log4Shell parity)',
    requireName: 'js-yaml',
  },
  deserial: {
    scenario: 'deserial',
    cveId: 'CVE-2017-5941',
    package: 'node-serialize',
    pinnedVersion: '0.0.4',
    severity: 'low',
    attackType: 'DESEREAL',
    description: 'Unsafe node-serialize unserialize on imported session blob',
    requireName: 'node-serialize',
  },
};

const ENDPOINTS_BY_SCENARIO = {
  rce: ['/api/v1/documents/convert', '/attack/rce-ejs'],
  ssrf: ['/api/v1/links/preview', '/attack/ssrf'],
  sqli: ['/api/v1/users/search', '/attack/sqli'],
  log4j: ['/api/v1/auth/login', '/attack/log4j'],
  deserial: ['/api/v1/sessions/import', '/attack/deserialization-node-serialize'],
};

const ROTATE_ORDER = ['sqli', 'log4j', 'ssrf', 'deserial', 'rce'];

const PATH_TO_SCENARIO = {
  '/api/v1/documents/convert': 'rce',
  '/attack/rce-ejs': 'rce',
  '/api/v1/links/preview': 'ssrf',
  '/attack/ssrf': 'ssrf',
  '/api/v1/users/search': 'sqli',
  '/attack/sqli': 'sqli',
  '/api/v1/auth/login': 'log4j',
  '/attack/log4j': 'log4j',
  '/api/v1/sessions/import': 'deserial',
  '/attack/deserialization-node-serialize': 'deserial',
};

function getTarget(scenario) {
  return VULNERABILITY_TARGETS[String(scenario || '').toLowerCase()] || null;
}

function vulnerabilityMetadata(scenario) {
  const target = getTarget(scenario);
  if (!target) {
    return {};
  }
  return {
    cve: target.cveId,
    package: target.package,
    version: target.pinnedVersion,
    severity: target.severity,
    attackType: target.attackType,
    description: target.description,
  };
}

function allTargetsSummary() {
  return Object.values(VULNERABILITY_TARGETS).map((t) => ({
    scenario: t.scenario,
    cve: t.cveId,
    package: t.package,
    version: t.pinnedVersion,
    severity: t.severity,
    attackType: t.attackType,
    endpoints: ENDPOINTS_BY_SCENARIO[t.scenario] || [],
  }));
}

module.exports = {
  VULNERABILITY_TARGETS,
  ENDPOINTS_BY_SCENARIO,
  ROTATE_ORDER,
  PATH_TO_SCENARIO,
  getTarget,
  vulnerabilityMetadata,
  allTargetsSummary,
};
