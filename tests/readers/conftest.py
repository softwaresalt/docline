"""Shared pytest fixtures for tests/readers/*.

Currently exposes:

* ``install_fake_adi_sdk`` — fixture-factory that stubs the
  ``azure.*`` SDK module hierarchy via ``monkeypatch.setitem`` so that
  tests can exercise ADI code paths without requiring the real
  ``azure-ai-documentintelligence`` package to be installed. Lifted
  from the per-file duplication that crept into
  ``test_adi_extractor.py`` and ``test_pdf_engine_routing.py`` during
  the 029-S spike (R5 Copilot review).

Class-identity invariant (R8 Copilot review)
--------------------------------------------
``_FakeAzureKeyCredential`` and ``_FakeAzureError`` are defined ONCE
at module scope rather than inside ``_stub_azure_module_tree``. Calling
``install_fake_adi_sdk(...)`` multiple times within a single test
(e.g. once with the default client, then again with a custom client)
MUST install the SAME exception class each time, otherwise
``isinstance`` checks and ``except AzureError`` clauses inside
production code under test would silently miss exceptions raised by
the first-installed class.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable

import pytest


class _FakeAzureKeyCredential:
    """Stable fake credential class shared across all fixture invocations."""

    def __init__(self, key: str) -> None:
        self.key = key


class _FakeAzureError(Exception):
    """Stable fake exception class shared across all fixture invocations.

    Module-scope so ``isinstance(exc, AzureError)`` works correctly
    after multiple ``install_fake_adi_sdk(...)`` calls within the
    same test (R8 Copilot review).
    """


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

    The credential and exception classes are stable module-level
    constants (see class-identity invariant in the module docstring).
    """
    monkeypatch.setitem(sys.modules, "azure", types.ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.core", types.ModuleType("azure.core"))

    creds_mod = types.ModuleType("azure.core.credentials")
    creds_mod.AzureKeyCredential = _FakeAzureKeyCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials", creds_mod)

    exc_mod = types.ModuleType("azure.core.exceptions")
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

    Successive calls within a single test reuse the same
    ``AzureKeyCredential`` and ``AzureError`` classes (see the
    class-identity invariant in the module docstring) so production
    code's ``except AzureError`` clauses and ``isinstance`` checks
    behave correctly across calls.
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
