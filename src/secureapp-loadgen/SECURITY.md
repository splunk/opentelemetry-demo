# secureapp-loadgen — SECURITY POLICY

## Intent

**This service is intentionally vulnerable.**

It exists to exercise vulnerability classes for Splunk SecureApp runtime-protection detection. Every CVE flagged against its dependencies is expected and load-bearing for the demo. Removing or upgrading those dependencies breaks the demo.

## Scope of intentional vulnerability

Scanners (Fossa, Dependabot, Snyk, Trivy, Grype, etc.) will report CVEs in the following categories. **All are intentional. Do not upgrade.**

| Class | Component | Purpose |
|-------|-----------|---------|
| RCE (Struts2 OGNL) | `org.apache.struts:struts2-core:2.3.12` | Simulates CVE-2017-5638 attack surface (`/api/v1/documents/convert`) |
| Log4Shell | `org.apache.logging.log4j:log4j-core:2.12.1` | Simulates CVE-2021-44228 attack surface (`/api/v1/auth/login`) |
| Deserialization | `commons-collections:commons-collections:3.2.1`, `org.keycloak:keycloak-common:10.0.2` | Simulates CVE-2020-1714-class attacks (`/api/v1/sessions/import`); the InvokerTransformer / KerberosSerializationUtils gadgets are the actual payload |
| SQLi target surface | Jetty 9.4.53 (`/api/v1/users/search`) | Server host for SQLi payload delivery |
| SSRF target surface | Jetty 9.4.53 (`/api/v1/links/preview`) | Server host for cloud-metadata SSRF payload delivery |

See `loadgen.sh` `ATTACK_ENTRIES` for the full endpoint → attack-class mapping.

## Scanner suppression policy

For each CVE reported against this manifest (`src/secureapp-loadgen/pom.xml`):

- **Do not open a fix PR.**
- **Do not run `mvn versions:use-latest-versions` or equivalent.**
- Suppress in the scanner with reason: **"Intentionally vulnerable demo target — see `src/secureapp-loadgen/SECURITY.md`."**

Fossa: mark issue as `Ignored` with justification pointing here. Dependabot: close alert with reason `Vulnerable code is not actually used` / `Risk is tolerable to this project` referencing this file.

## Not-in-scope for this policy

If a CVE lands in a dependency that is **not** part of the vulnerable-attack surface (e.g. a build-plugin CVE, a transitive test-only dependency with no runtime impact), a targeted upgrade is fine — but only if it does not remove or alter any of the classes listed above.

## Contact

Questions about whether a specific CVE is intentional here: check `loadgen.sh` first, then ask the SecureApp demo owner before upgrading.
