"""CVE-to-attack mapping for intentionally pinned vulnerable libraries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class VulnerabilityTarget:
    scenario: str
    cve_id: str
    package: str
    pinned_version: str
    severity: str
    attack_type: str
    description: str
    import_name: str


# Low/medium severity CVEs with installable pins on Python 3.11.
# Each HTTP attack scenario exercises its mapped library.
VULNERABILITY_TARGETS: Dict[str, VulnerabilityTarget] = {
    "rce": VulnerabilityTarget(
        scenario="rce",
        cve_id="CVE-2024-22195",
        package="jinja2",
        pinned_version="3.1.2",
        severity="low",
        attack_type="RCE",
        description="Jinja2 server-side template injection via unsafe template render",
        import_name="jinja2",
    ),
    "ssrf": VulnerabilityTarget(
        scenario="ssrf",
        cve_id="CVE-2021-33503",
        package="urllib3",
        pinned_version="1.26.5",
        severity="low",
        attack_type="SSRF",
        description="SSRF via requests/urllib3 fetch to cloud metadata endpoint",
        import_name="urllib3",
    ),
    "sqli": VulnerabilityTarget(
        scenario="sqli",
        cve_id="CVE-2022-21698",
        package="sqlalchemy",
        pinned_version="1.4.46",
        severity="low",
        attack_type="SQL",
        description="SQL injection via concatenated SQLAlchemy text() query",
        import_name="sqlalchemy",
    ),
    "log4j": VulnerabilityTarget(
        scenario="log4j",
        cve_id="CVE-2020-14343",
        package="pyyaml",
        pinned_version="5.3.1",
        severity="low",
        attack_type="LOG4J",
        description="Unsafe PyYAML load of JNDI-style credential payload (Log4Shell parity)",
        import_name="yaml",
    ),
    "deserial": VulnerabilityTarget(
        scenario="deserial",
        cve_id="CVE-2022-45199",
        package="pillow",
        pinned_version="9.2.0",
        severity="low",
        attack_type="DESEREAL",
        description="Pillow ImageMath.eval expression evaluation on imported session image",
        import_name="PIL",
    ),
}


def get_target(scenario: str) -> Optional[VulnerabilityTarget]:
    return VULNERABILITY_TARGETS.get(scenario.lower())


def vulnerability_metadata(scenario: str) -> dict:
    target = get_target(scenario)
    if target is None:
        return {}
    return {
        "cve": target.cve_id,
        "package": target.package,
        "version": target.pinned_version,
        "severity": target.severity,
        "attackType": target.attack_type,
        "description": target.description,
    }


def va_library_rotation() -> List[Tuple[str, str]]:
    """(import_name, short_name) pairs aligned with pinned vulnerable packages."""
    seen = set()
    libraries: List[Tuple[str, str]] = []
    for target in VULNERABILITY_TARGETS.values():
        key = (target.import_name, target.package)
        if key not in seen:
            seen.add(key)
            libraries.append(key)
    # requests is pulled in by SSRF path alongside urllib3
    if ("requests", "requests") not in seen:
        libraries.append(("requests", "requests"))
    return libraries


def all_targets_summary() -> List[dict]:
    return [
        {
            "scenario": t.scenario,
            "cve": t.cve_id,
            "package": t.package,
            "version": t.pinned_version,
            "severity": t.severity,
            "attackType": t.attack_type,
            "endpoints": ENDPOINTS_BY_SCENARIO.get(t.scenario, []),
        }
        for t in VULNERABILITY_TARGETS.values()
    ]


ENDPOINTS_BY_SCENARIO: Dict[str, List[str]] = {
    "rce": ["/api/v1/documents/convert", "/attack/rce-jinja2"],
    "ssrf": ["/api/v1/links/preview", "/attack/ssrf"],
    "sqli": ["/api/v1/users/search", "/attack/sqli"],
    "log4j": ["/api/v1/auth/login", "/attack/log4j"],
    "deserial": ["/api/v1/sessions/import", "/attack/deserialization-pillow"],
}
