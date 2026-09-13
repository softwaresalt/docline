"""Unit tests for ELT source-key sanitization helpers."""

from urllib.parse import quote

import pytest

from docline.elt.manifest_models import ManifestGitSource, ManifestLocalSource, ManifestUrlSource
from docline.elt.models import GitHubRepoSource, LocalFileSource, WebCrawlSource
from docline.elt.source_keys import build_source_key, sanitize_source_id, sanitize_source_key
from docline.fetch.staging import make_job_id

_SOURCE_URL_REDACTED = "<source-url-redacted>"


def _encode_name_layers(raw_name: str, layers: int) -> str:
    """Return *raw_name* with its percent signs encoded *layers* times."""
    current = raw_name
    for _ in range(layers):
        current = quote(current, safe="")
    return current


class TestSanitizeSourceKey:
    """Tests for typed-config source-key sanitization."""

    def test_redacts_crawl_url_credentials_and_preserves_options(self) -> None:
        """sanitize_source_key removes crawl URL credentials but keeps suffix options."""
        config = WebCrawlSource(
            type="web_crawl",
            url="https://user:pass@host/x?token=SECRET&other=1",
            depth=2,
            max_pages=5,
            domain_lock=False,
            rate_limit_ms=250,
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == (
            "web_crawl:https://host/x?other=1:depth=2:max_pages=5:"
            "domain_lock=false:rate_limit_ms=250"
        )
        assert "SECRET" not in sanitized
        assert "user:pass@" not in sanitized

    def test_redacts_malformed_crawl_url_without_raising(self) -> None:
        """sanitize_source_key fails closed for malformed crawl URLs."""
        config = WebCrawlSource(
            type="web_crawl",
            url="https://host:notaport?token=SECRET",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == f"web_crawl:{_SOURCE_URL_REDACTED}"
        assert "SECRET" not in sanitized

    @pytest.mark.parametrize(
        ("raw_id", "expected_id"),
        [
            (
                "https://user:pass@host/source?token=IDSECRET",
                "https://host/source?token=<redacted>",
            ),
            ("srcA?token=IDSECRET", "srcA?token=<redacted>"),
            (
                "https://host:notaport?token=IDSECRET",
                "https://host:notaport?token=<redacted>",
            ),
            ("/source-a", "/source-a"),
            ("https://host/x#frag", "https://host/x#frag"),
            ("https://host:notaport", "https://host:notaport"),
        ],
    )
    def test_manifest_url_source_uses_sanitized_ids(self, raw_id: str, expected_id: str) -> None:
        """Manifest URL source keys sanitize IDs without parsing malformed ports."""
        config = ManifestUrlSource(
            type="url",
            id=raw_id,
            url="https://example.com/docs",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == f"manifest_url:{expected_id}:https://example.com/docs"
        assert "IDSECRET" not in sanitized
        assert "user:pass@" not in sanitized

    @pytest.mark.parametrize(
        "config",
        [
            GitHubRepoSource(
                type="github_repo",
                repo_url="https://github.com/org/repo",
                branch="main",
                path_glob="**/*.md",
            ),
            LocalFileSource(type="local_file", paths=["docs/a.md", "docs/b.md"]),
        ],
    )
    def test_preserves_credential_free_non_url_configs_in_unit_scope(self, config) -> None:
        """Unit-1 scope leaves credential-free GitHub/local variants unchanged."""
        assert sanitize_source_key(config) == build_source_key(config)

    def test_redacts_credentialed_crawl_url_with_default_options(self) -> None:
        """sanitize_source_key keeps empty crawl option suffixes absent after redaction."""
        config = WebCrawlSource(
            type="web_crawl",
            url="https://user:pass@host/x?token=SECRET",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == "web_crawl:https://host/x"
        assert "SECRET" not in sanitized
        assert "user:pass@" not in sanitized

    def test_does_not_change_raw_build_source_key(self) -> None:
        """sanitize_source_key does not mutate the raw build_source_key contract."""
        config = WebCrawlSource(
            type="web_crawl",
            url="https://user:pass@host/x?token=SECRET",
            max_pages=3,
        )

        raw_before = build_source_key(config)
        sanitized = sanitize_source_key(config)
        raw_after = build_source_key(config)

        assert raw_before == raw_after
        assert "SECRET" in raw_before
        assert "SECRET" not in sanitized

    @pytest.mark.parametrize(
        ("repo_url", "expected_repo_url"),
        [
            (
                "https://user:pass@github.com/org/repo.git?token=SECRET&other=1",
                "https://github.com/org/repo.git?other=1",
            ),
            (
                "https://user:pass@github.com/org/repo.git?%2574oken=SECRET&other=1",
                "https://github.com/org/repo.git?other=1",
            ),
        ],
    )
    def test_redacts_github_repo_url_credentials(
        self,
        repo_url: str,
        expected_repo_url: str,
    ) -> None:
        """GitHub repo keys redact credential-bearing repo URLs."""
        config = GitHubRepoSource(
            type="github_repo",
            repo_url=repo_url,
            branch="main",
            path_glob="docs/**/*.md",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == f"github_repo:{expected_repo_url}@main:docs/**/*.md"
        assert "SECRET" not in sanitized
        assert "user:pass@" not in sanitized

    @pytest.mark.parametrize(
        ("raw_id", "expected_id"),
        [
            ("srcA?token=IDSECRET", "srcA?token=<redacted>"),
            ("srcA?%74oken=IDSECRET", "srcA?%74oken=<redacted>"),
            ("srcA?%2574oken=IDSECRET", "srcA?%2574oken=<redacted>"),
        ],
    )
    def test_redacts_manifest_git_url_and_id_credentials(
        self,
        raw_id: str,
        expected_id: str,
    ) -> None:
        """Manifest git keys redact both manifest IDs and repository URLs."""
        config = ManifestGitSource(
            type="git",
            id=raw_id,
            url="https://user:pass@github.com/org/repo.git?token=SECRET&other=1",
            branch="main",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == (
            f"manifest_git:{expected_id}:https://github.com/org/repo.git?other=1@main"
        )
        assert "IDSECRET" not in sanitized
        assert "SECRET" not in sanitized
        assert "user:pass@" not in sanitized

    def test_redacts_manifest_local_id_and_preserves_path_and_includes(self) -> None:
        """Manifest local keys redact IDs while keeping filesystem fields byte-identical."""
        config = ManifestLocalSource(
            type="local",
            id="srcA?token=IDSECRET",
            path="docs/source",
            include=["README.md", "**/*.md"],
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == "manifest_local:srcA?token=<redacted>:docs/source:**/*.md,README.md"
        assert "IDSECRET" not in sanitized
        assert ":docs/source:" in sanitized
        assert sanitized.endswith(":**/*.md,README.md")

    @pytest.mark.parametrize(
        "config",
        [
            GitHubRepoSource(
                type="github_repo",
                repo_url="https://github.com/org/repo.git",
                branch="main",
                path_glob="docs/**/*.md",
            ),
            ManifestGitSource(
                type="git",
                id="source-a",
                url="https://github.com/org/repo.git",
                branch="main",
            ),
            ManifestLocalSource(
                type="local",
                id="source-a",
                path="docs/source",
                include=["**/*.md"],
            ),
        ],
    )
    def test_preserves_credential_free_git_and_manifest_variants(self, config) -> None:
        """Credential-free git and manifest variants stay byte-identical."""
        assert sanitize_source_key(config) == build_source_key(config)

    @pytest.mark.parametrize(
        "config",
        [
            GitHubRepoSource(
                type="github_repo",
                repo_url="https://user:pass@github.com/org/repo.git?token=SECRET",
                branch="main",
                path_glob="docs/**/*.md",
            ),
            ManifestGitSource(
                type="git",
                id="srcA?token=IDSECRET",
                url="https://user:pass@github.com/org/repo.git?token=SECRET",
                branch="main",
            ),
            ManifestLocalSource(
                type="local",
                id="srcA?token=IDSECRET",
                path="docs/source",
                include=["**/*.md"],
            ),
        ],
    )
    def test_preserves_raw_job_id_input_for_new_variants(self, config) -> None:
        """sanitize_source_key leaves raw build_source_key/make_job_id inputs deterministic."""
        raw_before = build_source_key(config)
        sanitized = sanitize_source_key(config)
        raw_after = build_source_key(config)

        assert raw_before == raw_after
        assert make_job_id(raw_before) == make_job_id(raw_after)
        assert raw_before != sanitized

    @pytest.mark.parametrize(
        ("raw_branch", "expected_branch"),
        [
            ("main?token=SECRET", "main?token=<redacted>"),
            ("main?%2574oken=SECRET", "main?%2574oken=<redacted>"),
        ],
    )
    def test_redacts_github_repo_branch_credentials(
        self,
        raw_branch: str,
        expected_branch: str,
    ) -> None:
        """GitHub repo branch values flow through sanitize_source_id."""
        config = GitHubRepoSource(
            type="github_repo",
            repo_url="https://github.com/org/repo.git",
            branch=raw_branch,
            path_glob="**/*.md",
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == f"github_repo:https://github.com/org/repo.git@{expected_branch}:**/*.md"
        assert "SECRET" not in sanitized

    @pytest.mark.parametrize(
        ("raw_path_glob", "expected_path_glob"),
        [
            ("**/*.md?token=SECRET", "**/*.md?token=<redacted>"),
            ("**/*.md?%2574oken=SECRET", "**/*.md?%2574oken=<redacted>"),
        ],
    )
    def test_redacts_github_repo_path_glob_credentials(
        self,
        raw_path_glob: str,
        expected_path_glob: str,
    ) -> None:
        """GitHub repo path globs flow through sanitize_source_id."""
        config = GitHubRepoSource(
            type="github_repo",
            repo_url="https://github.com/org/repo.git",
            branch="main",
            path_glob=raw_path_glob,
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == f"github_repo:https://github.com/org/repo.git@main:{expected_path_glob}"
        assert "SECRET" not in sanitized

    @pytest.mark.parametrize(
        ("raw_branch", "expected_branch"),
        [
            ("main?token=SECRET", "main?token=<redacted>"),
            ("main?%2574oken=SECRET", "main?%2574oken=<redacted>"),
        ],
    )
    def test_redacts_manifest_git_branch_credentials(
        self,
        raw_branch: str,
        expected_branch: str,
    ) -> None:
        """Manifest git branch values flow through sanitize_source_id."""
        config = ManifestGitSource(
            type="git",
            id="source-a",
            url="https://github.com/org/repo.git",
            branch=raw_branch,
        )

        sanitized = sanitize_source_key(config)

        assert sanitized == (
            f"manifest_git:source-a:https://github.com/org/repo.git@{expected_branch}"
        )
        assert "SECRET" not in sanitized


class TestSanitizeSourceId:
    """Tests for marker-gated source ID sanitization."""

    @pytest.mark.parametrize(
        ("raw_id", "expected"),
        [
            ("srcA?%74oken=IDSECRET", "srcA?%74oken=<redacted>"),
            (
                "https://host/x?%74oken=IDSECRET",
                "https://host/x?%74oken=<redacted>",
            ),
            ("srcA?%2574oken=IDSECRET", "srcA?%2574oken=<redacted>"),
        ],
    )
    def test_redacts_percent_encoded_credential_name_values(
        self,
        raw_id: str,
        expected: str,
    ) -> None:
        """sanitize_source_id preserves encoded keys while redacting their values."""
        sanitized = sanitize_source_id(raw_id)

        assert sanitized == expected
        assert "IDSECRET" not in sanitized

    def test_fails_closed_when_name_is_still_decoding_at_cap(self) -> None:
        """sanitize_source_id redacts when a credential key is still decoding at the cap."""
        raw_key = _encode_name_layers("%74oken", 6)
        raw_id = f"srcA?{raw_key}=IDSECRET"

        sanitized = sanitize_source_id(raw_id)

        assert sanitized == f"srcA?{raw_key}=<redacted>"
        assert "IDSECRET" not in sanitized

    @pytest.mark.parametrize("raw_id", ["srcA?note=%zz", "srcA?b=%e0%80"])
    def test_preserves_credential_free_malformed_percent_values(self, raw_id: str) -> None:
        """sanitize_source_id keeps malformed percent sequences when no marker is present."""
        assert sanitize_source_id(raw_id) == raw_id

    def test_strips_colonless_userinfo(self) -> None:
        """sanitize_source_id strips a single colon-less userinfo token."""
        sanitized = sanitize_source_id("https://TOKEN@host/x")

        assert sanitized == "https://host/x"
        assert "TOKEN" not in sanitized

    def test_preserves_non_url_identifier_with_bare_at_sign(self) -> None:
        """sanitize_source_id preserves credential-free non-URL identifiers containing ``@``."""
        assert sanitize_source_id("release@2026") == "release@2026"

    def test_redacts_non_url_identifier_before_second_query_delimiter(self) -> None:
        """sanitize_source_id redacts a credential before later ``?`` segments."""
        sanitized = sanitize_source_id("srcA?token=SECRET?detail=x")

        assert sanitized.startswith("srcA?token=<redacted>")
        assert "SECRET" not in sanitized

    def test_redacts_non_url_identifier_after_second_query_delimiter(self) -> None:
        """sanitize_source_id redacts a credential after an earlier ``?`` segment."""
        sanitized = sanitize_source_id("srcA?detail=x?token=SECRET")

        assert sanitized == "srcA?detail=x?token=<redacted>"
        assert "SECRET" not in sanitized

    def test_redacts_percent_encoded_userinfo(self) -> None:
        """sanitize_source_id strips percent-encoded userinfo after decoded-view detection."""
        sanitized = sanitize_source_id("https://user%3Apass@host/x")

        assert sanitized == "https://host/x"
        assert "user%3Apass" not in sanitized
