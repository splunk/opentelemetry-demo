"""Base class for flagd-driven Kubernetes demo scenarios.

To add a scenario (for example OOM stall or node memory pressure):

  1. Copy modules/image_pull.py to modules/<name>.py
  2. Subclass ScenarioModule, set `name` + `flag_key`, implement reconcile()
  3. Add the flag to src/flagd/demo.flagd.json
  4. If the module needs extra Kubernetes verbs, extend the Role in
     k8s-scenario-controller-k8s.yaml (ConfigMaps/Services are already allowed)

The controller imports every non-underscore module in this package on
startup. No central registry to edit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ScenarioModule(ABC):
    """One flag → one cluster mutation.

    `flag_type` selects the OFREP value shape:
      boolean — on/off flags (ImagePullBackOff, future OOM toggle)
      string  — named variants (e.g. "off" / "normal" / "fast")
      number  — intensity (e.g. memory MiB, leak multiplier)
    """

    name: str
    flag_key: str
    flag_type: str = "boolean"
    default: Any = False
    enabled: bool = True

    def read_flag(self, flags) -> Any:
        if self.flag_type == "string":
            return flags.get_string(self.flag_key, str(self.default))
        if self.flag_type == "number":
            return flags.get_number(self.flag_key, self.default)
        return flags.get_boolean(self.flag_key, bool(self.default))

    @abstractmethod
    def reconcile(self, cluster, value: Any) -> None:
        """Make the namespace match `value`. Must be idempotent."""
