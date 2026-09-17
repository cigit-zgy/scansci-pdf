"""Fail-closed operating profiles for the paper_download integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

PROFILE_ENV = "SCANSCI_PDF_PROFILE"
PROFILE_NAMES = ("institution_bulk", "home_personal")

_COMMON_GUARDS: dict[str, Any] = {
    "download_strategy": "legal_only",
    "scihub_enabled": False,
    "scihub_domains": [],
    "use_tor_for_scihub": False,
    "tor_proxy": "",
    "tor_use_bridges": False,
    "network_proxy": "",
    "proxy_pool": "",
    "browser_static_proxy": "",
    "browser_restart_every": 0,
    "max_browser_workers": 1,
    "institutional_workers": 1,
    "scihub_browser_workers": 1,
    "scihub_turnstile_click": False,
    "scihub_browser_first": False,
    "flaresolverr_url": "",
    "download_si": False,
}

_PROFILES: dict[str, dict[str, Any]] = {
    "institution_bulk": {
        **_COMMON_GUARDS,
        "batch_default_lanes": True,
        "human_interaction_mode": "defer",
        "oa_browser_fallback": False,
        "auto_relogin": False,
    },
    "home_personal": {
        **_COMMON_GUARDS,
        "batch_default_lanes": False,
        "batch_workers": 1,
        "human_interaction_mode": "manual_sequential",
        "oa_browser_fallback": False,
        "auto_relogin": False,
    },
}


class ProfilePolicyError(ValueError):
    """An explicit caller option attempted to widen a project-safe profile."""


def apply_project_profile(config: dict[str, Any], profile: str | None = None) -> dict[str, Any]:
    """Return a copy with the named profile's non-overridable guards applied."""
    selected = (
        profile or os.environ.get(PROFILE_ENV) or config.get("project_profile") or ""
    ).strip()
    if not selected:
        return dict(config)
    if selected not in _PROFILES:
        raise ProfilePolicyError(
            f"unknown project profile {selected!r}; choose one of {', '.join(PROFILE_NAMES)}"
        )
    effective = dict(config)
    effective.update(_PROFILES[selected])
    effective["project_profile"] = selected
    return effective


def enforce_runtime_options(
    config: dict[str, Any],
    *,
    scihub_enabled: bool | None = None,
    use_tor: bool = False,
    strategy: str | None = None,
) -> None:
    """Reject per-call options that would bypass an active safe profile."""
    if not config.get("project_profile"):
        return
    if scihub_enabled is True:
        raise ProfilePolicyError("project profile forbids grey-source acquisition")
    if use_tor:
        raise ProfilePolicyError("project profile forbids Tor")
    if strategy and strategy != "legal_only":
        raise ProfilePolicyError("project profile requires download_strategy=legal_only")


@dataclass(frozen=True)
class TwoPhaseResults:
    """A projection of ScanSci result rows; it is not a persistence layer."""

    automatic: tuple[dict[str, Any], ...]
    deferred: tuple[dict[str, Any], ...]


def split_two_phase(results: list[dict[str, Any]]) -> TwoPhaseResults:
    """Separate completed automatic rows from explicitly deferred human rows."""
    deferred = tuple(row for row in results if row.get("status") == "deferred")
    automatic = tuple(row for row in results if row.get("status") != "deferred")
    return TwoPhaseResults(automatic=automatic, deferred=deferred)


def deferred_result(doi: str) -> dict[str, Any]:
    """Represent a human-required route without opening a browser or new ledger."""
    return {
        "doi": doi,
        "identifier": doi,
        "success": False,
        "status": "deferred",
        "reason": "human_attention_required",
        "source": "none",
    }
