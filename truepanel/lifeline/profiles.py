"""Model-specific service provenance for Project Lifeline.

Profiles are explicit and source-backed. Lifeline never guesses a chassis from
bay count, hostname, DMI fragments, or visual similarity. A deployment must
select a known profile before model-specific physical service can be unlocked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final


@dataclass(frozen=True)
class ServiceProfile:
    key: str
    manufacturer: str
    family: str
    models: tuple[str, ...]
    source_title: str
    source_url: str
    source_scope: str
    drive_service_supported: bool
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


QNAP_TVS_X71: Final = ServiceProfile(
    key="qnap-tvs-x71",
    manufacturer="QNAP",
    family="TVS-x71",
    models=("TVS-471", "TVS-671", "TVS-871"),
    source_title="QNAP TVS-x71 Series Hardware User Manual",
    source_url=(
        "https://download.qnap.com/TechnicalDocument/"
        "QNAP_TVS-x71-QNAP_Turbo_NAS_Hardware_Manual_ENG_20150330.pdf"
    ),
    source_scope="chassis safety, drive-bay service, and hot-swap capability",
    drive_service_supported=True,
    notes=(
        "Use TrueNAS documentation for pool/VDEV/offline/replace semantics.",
        "Use the QNAP hardware manual only for chassis and physical-service guidance.",
        "Do not substitute QTS storage-management UI procedures on a TrueNAS installation.",
    ),
)

_PROFILES: Final[dict[str, ServiceProfile]] = {
    QNAP_TVS_X71.key: QNAP_TVS_X71,
}


def service_profile(key: Any) -> ServiceProfile | None:
    return _PROFILES.get(str(key or "").strip().lower())


def service_profile_for_config(config: Any) -> ServiceProfile | None:
    """Resolve only an explicit configured service profile."""

    if not isinstance(config, dict):
        return None
    hardware = config.get("hardware")
    if not isinstance(hardware, dict):
        return None
    lifeline = hardware.get("lifeline")
    if not isinstance(lifeline, dict):
        return None
    return service_profile(lifeline.get("service_profile"))


def profile_keys() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))


__all__ = [
    "QNAP_TVS_X71",
    "ServiceProfile",
    "profile_keys",
    "service_profile",
    "service_profile_for_config",
]
