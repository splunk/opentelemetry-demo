"""VA hints for pinned vulnerable libraries (SecureApp dependency reporting)."""

from __future__ import annotations

import importlib
import logging
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

from team_portal.config import VaRuntimeMode, parse_va_stagger_interval_seconds
from team_portal.vulnerabilities import va_library_rotation

logger = logging.getLogger(__name__)

VA_LIBRARIES: List[Tuple[str, str]] = va_library_rotation()

_va_cursor = 0
_va_lock = threading.Lock()


@dataclass
class VaHintResult:
    index: int
    short_name: str
    loaded: bool
    failure_message: Optional[str] = None

    def to_json_dict(self) -> dict:
        payload = {
            "index": self.index,
            "library": self.short_name,
            "loaded": self.loaded,
        }
        if not self.loaded and self.failure_message:
            payload["error"] = self.failure_message
        return payload


def advance_va_hint() -> VaHintResult:
    global _va_cursor
    with _va_lock:
        index = _va_cursor % len(VA_LIBRARIES)
        _va_cursor += 1

    import_name, short_name = VA_LIBRARIES[index]
    try:
        importlib.import_module(import_name)
        result = VaHintResult(index=index, short_name=short_name, loaded=True)
        logger.info("[VA] loaded %s", short_name)
        return result
    except Exception as exc:  # noqa: BLE001 — intentional for VA hint reporting
        message = str(exc) or exc.__class__.__name__
        logger.info("[VA] %s: %s", short_name, message)
        return VaHintResult(
            index=index,
            short_name=short_name,
            loaded=False,
            failure_message=message,
        )


def start_va_scheduler(mode: VaRuntimeMode) -> None:
    if mode != VaRuntimeMode.SCHEDULER:
        return

    interval = parse_va_stagger_interval_seconds()

    def _run() -> None:
        import time

        while True:
            advance_va_hint()
            time.sleep(interval)

    thread = threading.Thread(target=_run, name="va-library-hint", daemon=True)
    thread.start()
    logger.info(
        "VA_RUNTIME_MODE=scheduler — 1 package hint every %ss", interval
    )
