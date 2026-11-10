"""Tests for SPA serving and static-asset cache busting (riskmatris.routes.spa)."""

import re

from app import get_static_version

# ---------------------------------------------------------------------------
# Static asset cache busting
# ---------------------------------------------------------------------------


class TestStaticCacheBusting:
    """index.html must always be served fresh, while JS/CSS are referenced
    with a content-based version so a stale cached script can never run
    against newer markup (regression: an old cached app.js crashed with
    'effectiveThresholdInfo is null' after a deploy)."""

    def test_index_html_references_versioned_assets(self, test_client):
        version = get_static_version()
        for path in ("/", "/s/ABC123"):
            resp = test_client.get(path)
            assert resp.status_code == 200
            assert f"/static/app.js?v={version}" in resp.text
            # Every stylesheet under static/css/ must be versioned
            css_links = re.findall(r'href="(/static/[^"]+\.css[^"]*)"', resp.text)
            assert len(css_links) >= 10
            for link in css_links:
                assert link.endswith(f"?v={version}")
            assert "/static/styles.css" not in resp.text
            # The asset content hash is injected into a meta tag so the client
            # can cache-bust the i18n JSON fetches (they are cached for a day)
            assert f'<meta name="static-version" content="{version}"' in resp.text
            assert "__STATIC_VERSION__" not in resp.text
            # The SPA shell itself must always be revalidated
            assert resp.headers["cache-control"] == "no-cache"

    def test_version_is_stable_and_short(self):
        assert get_static_version() == get_static_version()
        assert len(get_static_version()) == 12

    def test_ttl_hours_injected_into_info_text(self, monkeypatch, test_client):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_TTL_HOURS", 6)
        resp = test_client.get("/about")
        assert resp.status_code == 200
        assert "<strong>6</strong>" in resp.text
        # The placeholder must never leak to users
        assert "__TTL_HOURS__" not in resp.text
        # The landing page no longer carries the info text
        assert "__TTL_HOURS__" not in test_client.get("/").text


class TestAboutPage:
    """The /about page hosts the service info that used to clutter the landing
    page; it is served like the SPA shell (fresh, versioned assets)."""

    def test_about_page_served_with_versioned_assets(self, test_client):
        version = get_static_version()
        resp = test_client.get("/about")
        assert resp.status_code == 200
        assert f"/static/js/page.js?v={version}" in resp.text
        assert f'<meta name="static-version" content="{version}"' in resp.text
        assert "__STATIC_VERSION__" not in resp.text
        css_links = re.findall(r'href="(/static/[^"]+\.css[^"]*)"', resp.text)
        assert len(css_links) >= 10
        for link in css_links:
            assert link.endswith(f"?v={version}")
        assert resp.headers["cache-control"] == "no-cache"

    def test_landing_links_to_about(self, test_client):
        resp = test_client.get("/")
        assert resp.status_code == 200
        assert 'href="/about"' in resp.text
