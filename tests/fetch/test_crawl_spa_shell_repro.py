"""Characterization repro for 070.001-T (T1) — SPA app-shell yields one page.

Reproduces the operator-reported defect: crawling a JavaScript/SPA-rendered
documentation site (modeled on the Terraform Registry's Ember app-shell)
discovers **zero** eligible sub-links because ``docline``'s static-HTML link
extraction (``docline.fetch.crawl_links.extract_links``) cannot see anchors
that only materialize after client-side hydration from a JSON:API. The
fixture below mirrors the real, live-verified shape of
``https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs``: a
~9 KB Ember app-shell with exactly one ``<a>`` tag (an external link, not a
provider-doc sub-link), zero ``/docs/*`` sub-links, and no mdBook-style
``toc-*.js`` script (so the TOC-discovery fallback path also finds nothing).

Red-meaningful: the test passes today (0 sub-links discovered, 1 page
crawled) because that **is** the current, defective behavior — this harness
locks the defect so 070.010-T's fix can be proven against it via the
regression contract (unrecognized/disabled hosts stay byte-identical) and the
new integration harness (070.008-T) proves the *fixed* behavior for a
recognized host.

No production code changed in this task.
"""

import asyncio

import pytest

from docline.fetch.crawl import CrawlConfig, crawl
from docline.fetch.http import FetchResponse, RemainingByteBudget

_SPA_SHELL_URL = "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs"

# Mirrors the live-verified Ember app-shell: one external anchor, no
# ``/docs/*`` sub-links, no ``toc-*.js`` script, Ember/Glimmer markers present
# so the shape is recognizably an SPA shell rather than an ordinary static page.
_SPA_SHELL_BODY = """<!DOCTYPE html>
<html>
<head>
  <meta name="terraform-registry/config/environment" content="%7B%22modulePrefix%22%3A%22tf%22%7D">
  <title>azurerm provider | Terraform Registry</title>
</head>
<body>
  <div id="ember-app-shell"></div>
  <noscript>You need to enable JavaScript to run this app.</noscript>
  <a href="https://www.hashicorp.com/">HashiCorp</a>
  <script src="/assets/vendor-abc123.js"></script>
  <script src="/assets/terraform-registry-def456.js"></script>
</body>
</html>
"""


def _install_spa_shell_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch ``crawl.fetch_page`` to serve only the SPA shell fixture."""

    async def fake_fetch_page(
        url: str,
        *,
        timeout_seconds: float = 30.0,
        max_redirects: int = 5,
        budget: RemainingByteBudget | None = None,
        **_kwargs: object,
    ) -> FetchResponse:
        del timeout_seconds, max_redirects
        if budget is not None:
            budget.debit_attempt()
        return FetchResponse(url=url, status=200, content_type="text/html", body=_SPA_SHELL_BODY)

    monkeypatch.setattr("docline.fetch.crawl.fetch_page", fake_fetch_page)


def test_spa_app_shell_yields_exactly_one_crawled_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Today, crawling an SPA app-shell yields exactly one page (the defect)."""
    _install_spa_shell_fetch(monkeypatch)

    outcome = asyncio.run(crawl(_SPA_SHELL_URL, CrawlConfig(max_pages=50)))

    assert len(outcome.results) == 1, (
        "the SPA app-shell fixture must yield exactly one page under today's "
        "static-only discovery, documenting the operator-reported defect"
    )
    assert outcome.results[0].url == _SPA_SHELL_URL


def test_spa_app_shell_discovers_zero_eligible_sublinks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture's one anchor is external and out of scope: 0 discovered links."""
    from docline.fetch.crawl_links import extract_links

    links = extract_links(_SPA_SHELL_BODY, _SPA_SHELL_URL)

    # The single anchor resolves but is an off-host link relative to the start
    # URL, so it is not a ``/docs/*`` sub-link and would never be admitted
    # under domain-lock discovery either way.
    assert links == ["https://www.hashicorp.com/"]
    assert not any("/docs/" in link for link in links), (
        "the SPA shell must expose zero /docs/* sub-links via static extraction"
    )
