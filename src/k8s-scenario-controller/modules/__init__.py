"""Auto-discover ScenarioModule subclasses from this package."""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")


def load_modules() -> list[ScenarioModule]:
    """Import every modules/*.py file and instantiate enabled subclasses.

    Set SCENARIO_MODULES to a comma-separated list of module `name`s to
    run a subset (default: all enabled modules).
    """
    package = importlib.import_module("modules")
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        importlib.import_module(f"modules.{info.name}")

    instances = [
        cls()
        for cls in ScenarioModule.__subclasses__()
        if getattr(cls, "enabled", True)
    ]

    wanted = os.getenv("SCENARIO_MODULES", "*").strip()
    if wanted != "*":
        allow = {name.strip() for name in wanted.split(",") if name.strip()}
        instances = [mod for mod in instances if mod.name in allow]

    instances.sort(key=lambda mod: mod.name)
    log.info(
        "loaded %d scenario module(s): %s",
        len(instances),
        ", ".join(f"{m.name}({m.flag_key})" for m in instances) or "(none)",
    )
    return instances
