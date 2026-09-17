from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scansci_pdf import _publisher_strategies_core as publisher_core
from scansci_pdf import browser_backend, browser_cookies, browser_engine


def test_macos_background_command_uses_dedicated_profile_and_loopback(monkeypatch):
    monkeypatch.setattr(browser_backend.sys, "platform", "darwin")
    monkeypatch.setattr(
        browser_backend,
        "_chrome_executable",
        lambda: Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    )

    command = browser_backend._background_chrome_command(
        Path("/private/tmp/scansci-profile"), 43117, ["--disable-features=Example"]
    )

    assert command[:6] == [
        "/usr/bin/open",
        "-g",
        "-n",
        "-W",
        "-a",
        "/Applications/Google Chrome.app",
    ]
    assert "--user-data-dir=/private/tmp/scansci-profile" in command
    assert "--no-startup-window" in command
    assert "--remote-debugging-address=127.0.0.1" in command
    assert "--remote-debugging-port=43117" in command
    assert "--disable-features=Example" in command
    assert "about:blank" not in command


def test_background_context_creates_only_background_target(tmp_path):
    raw_context = MagicMock()
    created_page = object()
    expected = MagicMock()
    expected.__enter__.return_value.value = created_page
    raw_context.expect_page.return_value = expected
    session = MagicMock()
    browser = MagicMock()
    browser.is_connected.return_value = True
    process = MagicMock()
    owner = browser_backend._BackgroundPersistentContext(
        browser=browser,
        context=raw_context,
        session=session,
        process=process,
        profile=tmp_path / "scansci-profile",
        playwright=MagicMock(),
    )

    assert owner.new_page() is created_page
    session.send.assert_called_once_with(
        "Target.createTarget", {"url": "about:blank", "background": True}
    )
    raw_context.new_page.assert_not_called()


def test_headed_patchright_persistent_launch_uses_background_owner(monkeypatch, tmp_path):
    sentinel = object()
    background = MagicMock(return_value=sentinel)
    native = MagicMock()
    monkeypatch.setattr(browser_backend.sys, "platform", "darwin")
    monkeypatch.setattr(browser_backend, "_launch_patchright_background_persistent", background)
    monkeypatch.setattr(
        browser_backend,
        "sync_playwright",
        SimpleNamespace(start=lambda: SimpleNamespace(chromium=native)),
        raising=False,
    )

    profile = str(tmp_path / "scansci-profile")
    result = browser_backend._launch_patchright_persistent({}, profile, False, None, ["--flag"])

    assert result is sentinel
    background.assert_called_once_with({}, profile, ["--flag"])
    native.launch_persistent_context.assert_not_called()


def test_ordinary_chrome_profile_is_rejected():
    ordinary = Path.home() / "Library/Application Support/Google/Chrome"
    with pytest.raises(RuntimeError, match="ordinary Chrome profile"):
        browser_backend._validate_dedicated_profile(ordinary)


def test_shared_headed_browser_reuses_data_scoped_persistent_profile(monkeypatch, tmp_path):
    context = MagicMock()
    context.browser = context
    context.is_connected.return_value = True
    persistent = MagicMock(return_value=context)
    monkeypatch.setattr(browser_engine, "get_persistent_context", persistent)
    monkeypatch.setattr(browser_engine, "_check_browser_backend", lambda _cfg: True)
    monkeypatch.setattr(browser_engine, "resolve_backend", lambda _cfg: "patchright")
    monkeypatch.setenv("SCANSCI_PDF_DATA_DIR", str(tmp_path))
    for name in ("browser", "context"):
        if hasattr(browser_engine._tls, name):
            delattr(browser_engine._tls, name)

    browser, returned_context = browser_engine._get_shared_browser(
        {"browser_backend": "patchright", "browser_headless": False}
    )

    assert browser is context
    assert returned_context is context
    persistent.assert_called_once_with(
        tmp_path / "browser_profiles" / "publisher",
        {"browser_backend": "patchright", "browser_headless": False},
    )

    browser_engine.close_shared_browser()


def test_publisher_login_captures_state_from_the_same_persistent_profile(monkeypatch, tmp_path):
    page = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    context.cookies.return_value = [
        {
            "name": f"publisher-{index}",
            "value": "value",
            "domain": ".sciencedirect.com",
            "path": "/",
        }
        for index in range(4)
    ]
    persistent = MagicMock(return_value=context)
    monkeypatch.setattr(browser_engine, "get_persistent_context", persistent)
    profile = tmp_path / "profile"

    result = browser_cookies.extract_via_browser(
        {
            "cache_dir": str(tmp_path / "cache"),
            "chrome_profile_dir": str(profile),
        },
        max_wait=1,
    )

    assert result["success"] is True
    persistent.assert_called_once_with(
        profile,
        {
            "cache_dir": str(tmp_path / "cache"),
            "chrome_profile_dir": str(profile),
        },
    )
    context.new_context.assert_not_called()
    context.close.assert_called_once()


def test_visible_publisher_fallback_reuses_the_shared_persistent_owner(monkeypatch, tmp_path):
    page = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    persistent = MagicMock(return_value=context)
    monkeypatch.setattr(browser_engine, "get_persistent_context", persistent)
    monkeypatch.setattr(browser_engine, "is_available", lambda _cfg: True)
    monkeypatch.setattr(browser_engine, "close_shared_browser", lambda _cfg: None)
    profile = tmp_path / "publisher-profile"
    config = {"chrome_profile_dir": str(profile), "browser_backend": "patchright"}

    with publisher_core._visible_browser(config, "Elsevier") as (ctx, returned_page):
        assert ctx is context
        assert returned_page is page

    persistent.assert_called_once_with(profile, config)
    context.close.assert_called_once()


def test_elsevier_entitlement_requires_a_multi_page_pdf():
    assert (
        publisher_core._elsevier_entitlement_state(
            "Access provided by Example University", pdf_pages=12
        )
        == "subscribed_full_text"
    )
    assert (
        publisher_core._elsevier_entitlement_state(
            "Example University does not subscribe to this content on ScienceDirect.",
            pdf_pages=0,
        )
        == "institution_not_subscribed"
    )
    assert (
        publisher_core._elsevier_entitlement_state(
            "Access provided by Example University", pdf_pages=1
        )
        == "preview_only"
    )
