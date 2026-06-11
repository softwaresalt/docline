"""Shared pytest fixtures for tests/readers/*.

Currently exposes:

* ``install_fake_adi_sdk`` — fixture-factory that stubs the
  ``azure.*`` SDK module hierarchy via ``monkeypatch.setitem`` so that
  tests can exercise ADI code paths without requiring the real
  ``azure-ai-documentintelligence`` package to be installed. Lifted
  from the per-file duplication that crept into
  ``test_adi_extractor.py`` and ``test_pdf_engine_routing.py`` during
  the 029-S spike (R5 Copilot review).
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable

import pytest


def _stub_azure_module_tree(
    monkeypatch: pytest.MonkeyPatch,
    di_client_cls: type,
) -> None:
    """Install minimal fake ``azure.*`` modules with the given client class.

    The caller supplies the DocumentIntelligenceClient stub so each
    test can shape it (return canned content, raise specific errors,
    record call kwargs, etc.) without touching the rest of the SDK
    surface.

    All entries are installed via ``monkeypatch.setitem(sys.modules,
    ...)`` so pytest automatically rolls them back at test teardown.
    """
    monkeypatch.setitem(sys.modules, "azure", types.ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.core", types.ModuleType("azure.core"))

    creds_mod = types.ModuleType("azure.core.credentials")

    class _FakeAzureKeyCredential:
        def __init__(self, key: str) -> None:
            self.key = key

    creds_mod.AzureKeyCredential = _FakeAzureKeyCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials", creds_mod)

    exc_mod = types.ModuleType("azure.core.exceptions")

    class _FakeAzureError(Exception):
        pass

    exc_mod.AzureError = _FakeAzureError
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", exc_mod)

    monkeypatch.setitem(sys.modules, "azure.ai", types.ModuleType("azure.ai"))

    di_mod = types.ModuleType("azure.ai.documentintelligence")
    di_mod.DocumentIntelligenceClient = di_client_cls
    monkeypatch.setitem(sys.modules, "azure.ai.documentintelligence", di_mod)


@pytest.fixture
def install_fake_adi_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., None]:
    """Returns a callable that installs the fake ``azure.*`` SDK tree.

    Two calling conventions:

    1. ``install_fake_adi_sdk()`` — uses a default no-op client that
       returns canned markdown content via ``content`` kwarg
       (default ``"# Mock content\n\nbody"``) and records the last call
       kwargs on ``DocumentIntelligenceClient.last_call``.

    2. ``install_fake_adi_sdk(client_cls=MyClient)`` — installs
       ``MyClient`` as the ``DocumentIntelligenceClient`` so the
       caller can fully customize behavior (e.g. raise a specific
       error to simulate a transient cloud failure).
    """

    def _install(
        *,
        content: str = "# Mock content\n\nbody",
        client_cls: type | None = None,
    ) -> None:
        if client_cls is None:

            class _FakeResult:
                def __init__(self, content_value: str, pages: int) -> None:
                    self.content = content_value
                    self.pages = [object()] * pages

            class _FakePoller:
                def __init__(self, result_value: object) -> None:
                    self._r = result_value

                def result(self) -> object:
                    return self._r

            class _DefaultClient:
                last_call: dict[str, object] = {}

                def __init__(self, *, endpoint: str, credential: object) -> None:
                    self.endpoint = endpoint
                    self.credential = credential

                def begin_analyze_document(self, **kwargs: object) -> _FakePoller:
                    _DefaultClient.last_call = kwargs
                    return _FakePoller(_FakeResult(content, pages=3))

            client_cls = _DefaultClient
        _stub_azure_module_tree(monkeypatch, client_cls)

    return _install
