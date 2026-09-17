from __future__ import annotations

from scansci_pdf import config as config_mod
from scansci_pdf import main, pipeline
from scansci_pdf.project_profiles import (
    PROFILE_NAMES,
    ProfilePolicyError,
    apply_project_profile,
    split_two_phase,
)
from scansci_pdf.sources import _build_free_sources, batch_download, download


def test_profiles_apply_non_overridable_excluded_route_guards():
    hostile = {
        "scihub_enabled": True,
        "use_tor_for_scihub": True,
        "tor_proxy": "socks5://127.0.0.1:9050",
        "proxy_pool": "http://one,http://two",
        "browser_static_proxy": "socks5://proxy",
        "scihub_turnstile_click": True,
        "flaresolverr_url": "http://solver",
        "download_strategy": "grey_only",
        "download_si": True,
    }
    for name in PROFILE_NAMES:
        cfg = apply_project_profile(hostile, name)
        assert cfg["download_strategy"] == "legal_only"
        assert cfg["scihub_enabled"] is False
        assert cfg["scihub_domains"] == []
        assert cfg["use_tor_for_scihub"] is False
        assert cfg["tor_proxy"] == ""
        assert cfg["network_proxy"] == ""
        assert cfg["proxy_pool"] == ""
        assert cfg["browser_static_proxy"] == ""
        assert cfg["browser_restart_every"] == 0
        assert cfg["max_browser_workers"] == 1
        assert cfg["institutional_workers"] == 1
        assert cfg["scihub_browser_workers"] == 1
        assert cfg["scihub_turnstile_click"] is False
        assert cfg["flaresolverr_url"] == ""
        assert cfg["download_si"] is False


def test_safe_profiles_build_only_legal_source_candidates():
    for name in PROFILE_NAMES:
        labels = {
            label
            for _, label in _build_free_sources("10.1000/profile", apply_project_profile({}, name))
        }
        assert {"Sci-Hub", "SciBban", "LibGen"}.isdisjoint(labels)
        assert {"Unpaywall", "OpenAlexOA", "SemanticScholar"}.issubset(labels)


def test_environment_profile_overrides_unsafe_saved_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "missing.json")
    monkeypatch.setenv("SCANSCI_PDF_PROFILE", "institution_bulk")
    cfg = config_mod.load_config()
    assert cfg["project_profile"] == "institution_bulk"
    assert cfg["human_interaction_mode"] == "defer"
    assert cfg["scihub_enabled"] is False


def test_unknown_profile_fails_closed():
    try:
        apply_project_profile({}, "typo")
    except ProfilePolicyError as exc:
        assert "unknown project profile" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unknown profiles must fail closed")


def test_explicit_grey_and_tor_requests_stop_before_network(monkeypatch, tmp_path):
    monkeypatch.setenv("SCANSCI_PDF_PROFILE", "institution_bulk")
    called = []
    monkeypatch.setattr(
        "scansci_pdf.identifiers.validate_doi",
        lambda *_: called.append("network") or (True, ""),
    )
    one = download("10.1000/profile", tmp_path, scihub_enabled=True)
    many = batch_download(["10.1000/profile"], tmp_path, use_tor=True)
    assert one["error_type"] == "profile_policy_blocked"
    assert many["results"][0]["error_type"] == "profile_policy_blocked"
    assert called == []


def test_institution_bulk_finishes_automatic_work_and_defers_human_lane(monkeypatch, tmp_path):
    entries = [
        pipeline.QueueEntry("10.1000/oa", channel="oa", oa_url="https://repo/a.pdf"),
        pipeline.QueueEntry("10.1000/human", channel="auto"),
    ]
    monkeypatch.setattr(
        pipeline,
        "_run_fast_lane",
        lambda *_args, **_kwargs: [
            {"doi": "10.1000/oa", "success": True, "source": "openalex", "file": "a.pdf"}
        ],
    )
    monkeypatch.setattr(pipeline, "_enrich_oa_urls", lambda *_: None)
    monkeypatch.setattr(pipeline, "_transient_retry", lambda *_: None)
    monkeypatch.setattr(pipeline, "_fetch_si_for_results", lambda *_: None)

    results = pipeline.run_lanes(
        entries,
        tmp_path,
        config={"project_profile": "institution_bulk"},
    )
    phases = split_two_phase(results)

    assert [r["doi"] for r in phases.automatic] == ["10.1000/oa"]
    assert [r["doi"] for r in phases.deferred] == ["10.1000/human"]
    assert phases.deferred[0]["reason"] == "human_attention_required"


def test_home_personal_is_sequential_and_keeps_manual_human_mode():
    cfg = apply_project_profile({"batch_workers": 12, "max_browser_workers": 5}, "home_personal")
    assert cfg["batch_workers"] == 1
    assert cfg["max_browser_workers"] == 1
    assert cfg["human_interaction_mode"] == "manual_sequential"


def test_config_set_never_echoes_elsevier_secret(monkeypatch, capsys):
    sentinel = "fixture-elsevier-value"
    monkeypatch.setattr(config_mod, "update_config", lambda *_: {})
    monkeypatch.setattr(main, "update_config", lambda *_: {}, raising=False)
    main.config_show("elsevier_api_key", sentinel)
    output = capsys.readouterr().out
    assert sentinel not in output
    assert "***" in output
