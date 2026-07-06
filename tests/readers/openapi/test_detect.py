"""Tests for OpenAPI/Swagger content-sniff detection (050.001-T / T1)."""

import json
from pathlib import Path

from docline.readers.openapi.detect import (
    detect_openapi_file,
    is_openapi_spec,
    openapi_kind,
)
from docline.router import classify_source
from docline.types import SourceKind

_OPENAPI_31_JSON = json.dumps(
    {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {},
    }
)

_OPENAPI_30_YAML = """openapi: 3.0.3
info:
  title: Demo
  version: 1.0.0
paths: {}
"""

_SWAGGER_20_JSON = json.dumps(
    {"swagger": "2.0", "info": {"title": "Legacy", "version": "1.0"}, "paths": {}}
)

_PLAIN_CONFIG_JSON = json.dumps(
    {"build": {"content": []}, "docsets_to_publish": [{"docset_name": "x"}]}
)


def test_openapi_31_json_detected() -> None:
    """An OpenAPI 3.1 JSON document sniffs as openapi-3.x."""
    assert openapi_kind(_OPENAPI_31_JSON) == "openapi-3.x"
    assert is_openapi_spec(_OPENAPI_31_JSON) is True


def test_openapi_30_yaml_detected() -> None:
    """An OpenAPI 3.0 YAML document sniffs as openapi-3.x."""
    assert openapi_kind(_OPENAPI_30_YAML) == "openapi-3.x"
    assert is_openapi_spec(_OPENAPI_30_YAML) is True


def test_swagger_20_detected() -> None:
    """A Swagger 2.0 document is recognized (rendering deferred, detection only)."""
    assert openapi_kind(_SWAGGER_20_JSON) == "swagger-2.0"
    assert is_openapi_spec(_SWAGGER_20_JSON) is True


def test_plain_config_json_not_openapi() -> None:
    """A plain docfx/publish config JSON is NOT classified as OpenAPI."""
    assert openapi_kind(_PLAIN_CONFIG_JSON) is None
    assert is_openapi_spec(_PLAIN_CONFIG_JSON) is False


def test_empty_text_not_openapi() -> None:
    """Empty or whitespace input is not OpenAPI and does not raise."""
    assert is_openapi_spec("") is False
    assert is_openapi_spec("   \n  ") is False


def test_malformed_text_not_openapi() -> None:
    """Unparseable content is not OpenAPI and does not raise."""
    assert is_openapi_spec("{ this is : not : valid : json") is False


def test_openapi_key_non_string_ignored() -> None:
    """A config whose ``openapi`` key is non-string is not misclassified."""
    assert is_openapi_spec(json.dumps({"openapi": True, "paths": {}})) is False


def test_non_mapping_root_not_openapi() -> None:
    """A JSON array root is not OpenAPI."""
    assert is_openapi_spec(json.dumps([1, 2, 3])) is False


def test_detect_openapi_file_positive(tmp_path: Path) -> None:
    """detect_openapi_file returns True for a spec file (JSON or YAML)."""
    spec = tmp_path / "spec.json"
    spec.write_text(_OPENAPI_31_JSON, encoding="utf-8")
    assert detect_openapi_file(spec) is True

    yaml_spec = tmp_path / "spec.yaml"
    yaml_spec.write_text(_OPENAPI_30_YAML, encoding="utf-8")
    assert detect_openapi_file(yaml_spec) is True


def test_detect_openapi_file_negative(tmp_path: Path) -> None:
    """detect_openapi_file returns False for a config file and missing file."""
    cfg = tmp_path / "docfx.json"
    cfg.write_text(_PLAIN_CONFIG_JSON, encoding="utf-8")
    assert detect_openapi_file(cfg) is False
    assert detect_openapi_file(tmp_path / "missing.json") is False


def test_classify_source_content_openapi() -> None:
    """classify_source with OpenAPI content classifies as OPENAPI."""
    result = classify_source("api/spec.json", content=_OPENAPI_31_JSON)
    assert result.kind == SourceKind.OPENAPI
    assert result.raw == "api/spec.json"


def test_classify_source_content_config_stays_file() -> None:
    """classify_source with non-spec content falls back to FILE."""
    result = classify_source("docfx.json", content=_PLAIN_CONFIG_JSON)
    assert result.kind == SourceKind.FILE


def test_classify_source_url_ignores_content() -> None:
    """A URL is classified as URL even if content sniffs as OpenAPI."""
    result = classify_source("https://example.com/spec.json", content=_OPENAPI_31_JSON)
    assert result.kind == SourceKind.URL


def test_classify_source_backcompat_no_content() -> None:
    """classify_source without content preserves existing FILE behavior."""
    assert classify_source("document.pdf").kind == SourceKind.FILE
