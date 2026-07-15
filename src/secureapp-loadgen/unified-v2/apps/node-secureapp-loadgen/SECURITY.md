# node-secureapp-loadgen — SECURITY POLICY

## Intent

**This service is intentionally vulnerable.**

It exists to exercise vulnerability classes for Splunk SecureApp runtime-protection detection. Every CVE flagged against its dependencies is expected and load-bearing for the demo. Removing or upgrading those dependencies breaks the demo.

## Scope of intentional vulnerability

Scanners (Fossa, Dependabot, Snyk, Trivy, Grype, etc.) will report CVEs in the following categories. **All are intentional. Do not upgrade.**

| Class | Component | Purpose |
|-------|-----------|---------|
| RCE / SSTI | `ejs@2.7.4` | Simulates CVE-2022-29078 attack surface (`/api/v1/documents/convert`) |
| Log4Shell parity | `js-yaml@3.13.1` | Simulates CVE-2020-14343 unsafe `yaml.load` attack surface (`/api/v1/auth/login`) |
| Deserialization | `node-serialize@0.0.4` | Simulates CVE-2017-5941 unsafe `unserialize` attack surface (`/api/v1/sessions/import`) |
| SQLi | `better-sqlite3@^11.7.0` | Simulates CVE-2022-25897 concatenated-query attack surface (`/api/v1/users/search`) |
| SSRF | `axios@0.21.1` | Simulates CVE-2021-3749-class cloud-metadata SSRF (`/api/v1/links/preview`) |

See `src/vulnerabilities.js` for the full scenario → CVE → package mapping, and `k8s/loadgen/loadgen-entries.sh` (node entries) for the endpoint → attack-class mapping.

## Scanner suppression policy

For each CVE reported against this manifest (`package.json`):

- **Do not open a fix PR.**
- **Do not run `npm update` or equivalent bulk upgrades on pinned packages.**
- Suppress in the scanner with reason: **"Intentionally vulnerable demo target — see `apps/node-secureapp-loadgen/SECURITY.md`."**

Fossa: mark issue as `Ignored` with justification pointing here. Dependabot: close alert with reason `Vulnerable code is not actually used` / `Risk is tolerable to this project` referencing this file.

## Not-in-scope for this policy

If a CVE lands in a dependency that is **not** part of the vulnerable-attack surface (e.g. a devDependency, a transitive build-only package with no runtime impact, or Express/`@splunk/otel` packages unrelated to the attack mapping), a targeted upgrade is fine — but only if it does not remove or alter any of the classes listed above.

## Contact

Questions about whether a specific CVE is intentional here: check `src/vulnerabilities.js` first, then ask the SecureApp demo owner before upgrading.
