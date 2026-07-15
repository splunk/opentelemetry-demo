# python-secureapp-loadgen — SECURITY POLICY

## Intent

**This service is intentionally vulnerable.**

It exists to exercise vulnerability classes for Splunk SecureApp runtime-protection detection. Every CVE flagged against its dependencies is expected and load-bearing for the demo. Removing or upgrading those dependencies breaks the demo.

## Scope of intentional vulnerability

Scanners (Fossa, Dependabot, Snyk, Trivy, Grype, etc.) will report CVEs in the following categories. **All are intentional. Do not upgrade.**

| Class | Component | Purpose |
|-------|-----------|---------|
| RCE / SSTI | `Jinja2==3.1.2` | Simulates CVE-2024-22195 attack surface (`/api/v1/documents/convert`) |
| Log4Shell parity | `PyYAML==5.3.1` | Simulates CVE-2020-14343 unsafe `yaml.load` attack surface (`/api/v1/auth/login`) |
| Deserialization | `Pillow==9.2.0` | Simulates CVE-2022-45199 `ImageMath.eval` attack surface (`/api/v1/sessions/import`) |
| SQLi | `SQLAlchemy==1.4.46` | Simulates CVE-2022-21698 concatenated-query attack surface (`/api/v1/users/search`) |
| SSRF | `urllib3==1.26.5`, `requests==2.25.1` | Simulates CVE-2021-33503-class cloud-metadata SSRF (`/api/v1/links/preview`) |

See `src/team_portal/vulnerabilities.py` for the full scenario → CVE → package mapping, and `k8s/loadgen/loadgen-entries.sh` (python entries) for the endpoint → attack-class mapping.

## Scanner suppression policy

For each CVE reported against this manifest (`requirements.txt`):

- **Do not open a fix PR.**
- **Do not run `pip install --upgrade` or equivalent bulk upgrades on pinned packages.**
- Suppress in the scanner with reason: **"Intentionally vulnerable demo target — see `apps/python-secureapp-loadgen/SECURITY.md`."**

Fossa: mark issue as `Ignored` with justification pointing here. Dependabot: close alert with reason `Vulnerable code is not actually used` / `Risk is tolerable to this project` referencing this file.

## Not-in-scope for this policy

If a CVE lands in a dependency that is **not** part of the vulnerable-attack surface (e.g. a build-only tool, a transitive test-only dependency with no runtime impact, or Flask/gunicorn/Splunk OTel packages unrelated to the attack mapping), a targeted upgrade is fine — but only if it does not remove or alter any of the classes listed above.

## Contact

Questions about whether a specific CVE is intentional here: check `src/team_portal/vulnerabilities.py` first, then ask the SecureApp demo owner before upgrading.
