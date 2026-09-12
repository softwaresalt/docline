#!/usr/bin/env python
"""Temporary, disposable HashiCorp unified-docs MDX -> MD normalization
preprocessor (shipment 062-S / feature 071-F).

Selectively copies ONLY the latest-version directory of every versioned
HashiCorp product, plus the entire tree of every unversioned product,
from a read-only external corpus (the HashiCorp unified-docs
``content/`` directory), converting ``.mdx`` to standard ``.md`` in
flight. This is disposable requirements-evidence tooling for a future
first-class docline MDX ingestion feature -- it is NOT integrated into
the docline application and is not intended to be maintained long-term.
See
``docs/design-docs/2026-09-11-hashicorp-mdx-normalization-requirements-evidence.md``
for the full rationale, scope boundary, and live-verification findings.

HARD CONTAINMENT CONTRACT
=========================
* Dry-run is the default mode: the tool performs ZERO writes -- including
  the ``--report`` file -- and prints a JSON plan (per-product selected
  version, file counts, fallback/ambiguous/unresolved MDX-construct
  tallies, warnings) to stdout only. ``--execute`` is REQUIRED to write
  anything to disk. If ``--report`` is supplied in dry-run mode, it is
  silently ignored for writing purposes (a note is printed to stderr);
  the plan is still available on stdout.
* Every write, in ``--execute`` mode, is guarded to resolve strictly
  inside ``--dest`` (:func:`guard_write_path` /
  :class:`ContainmentViolation`), including the ``--report`` file itself
  when one is supplied. A resolved write path outside ``--dest`` is
  refused and the process exits non-zero BEFORE any corpus write begins
  (fail-fast). The guard is re-applied again immediately before the
  report is actually written (review-fix cycle 2, finding 2) so the
  write always targets the freshly re-resolved path, never a
  possibly-stale resolution computed earlier in the run -- this is a
  best-effort containment check, not a race-free guarantee: Python's
  ``Path.resolve()`` cannot atomically bind a check to a subsequent
  write any more than any other check-then-act filesystem sequence can.
  A ``--report`` path resolving to EXACTLY the reserved claim sentinel
  name under ``--dest`` (``CLAIM_SENTINEL_NAME``) is a further, distinct
  rejection (``EXIT_REPORT_PATH_RESERVED``, review-fix cycle 3
  independent-review finding): plain containment alone does not catch
  this, since the reserved name is trivially inside ``--dest`` too, but
  writing there would overwrite the live sentinel and then have it
  deleted by the end-of-run claim-release cleanup, silently losing the
  report while the run still reports success.
* ``--execute`` accepts ``--dest`` ABSENT or EXISTING-AND-EMPTY -- never a
  pre-existing non-empty destination (review-fix cycle 3, reinstating the
  "existing empty is fine" ergonomics that cycle 2's atomic-claim redesign
  had incidentally narrowed away, while KEEPING that redesign's mutual-
  exclusion guarantee). ``--dest`` is claimed via :func:`claim_destination`
  immediately before any corpus write begins: an absent ``--dest`` is
  created and then claimed; an existing ``--dest`` must contain no entries
  before it is claimed. Either way, the actual claim is an exclusive
  OS-level create (``os.O_CREAT | os.O_EXCL``) of a small sentinel file
  directly under ``--dest`` -- never a deletion, replacement, or overlay of
  pre-existing content. Of two invocations racing for the same ``--dest``,
  exactly one wins the sentinel create and the other fails closed
  (``EXIT_DEST_ALREADY_EXISTS`` if the sentinel already exists at claim
  time, ``EXIT_DEST_NOT_EMPTY`` if other content is present) instead of
  silently interleaving output with the winner. Immediately after the
  sentinel is created, ``--dest`` is re-listed to confirm the sentinel is
  the ONLY entry present, rejecting (and releasing the sentinel) if
  anything else appeared in the interim. This mutual-exclusion guarantee
  covers races BETWEEN COOPERATING INVOCATIONS OF THIS SAME SCRIPT -- it is
  not, and does not claim to be, protection against an arbitrary
  non-cooperating writer dropping content into ``--dest`` at an arbitrary
  time; see :func:`claim_destination`'s docstring for the precise residual
  race limitations. The sentinel this invocation creates is always removed
  when the run finishes, success or failure, via a ``finally`` block in
  :func:`main` -- but ``--dest`` itself, and any partial or complete
  corpus/report output, is never removed. A claim failure for any reason
  other than pre-existing content or a concurrent claim (permission
  denial, a blocked ancestor path component, disk exhaustion, etc.) is
  reported distinctly (``EXIT_DEST_CLAIM_FAILED``) rather than escaping as
  a raw traceback; no output is written in that case, since the claim
  itself never succeeded. If a later step in the same run fails after
  ``--dest`` was successfully claimed, the partial output is left in place
  (never auto-deleted) and reported clearly as a failed, partial run
  (``EXIT_EXECUTION_FAILED``); if the corpus write pass succeeds but the
  subsequent ``--report`` write itself then fails, that is also reported
  distinctly (``EXIT_REPORT_WRITE_FAILED``) with the already-successful
  corpus output left in place. Dry-run is exempt from this check, and from
  claiming ``--dest``, entirely: it may point ``--dest`` anywhere,
  including a non-empty directory, without ever creating, claiming, or
  touching it.
* ``--execute`` performs a complete READ-ONLY normalization preflight
  pass (identical selection/normalization logic, zero writes) BEFORE
  ``--dest`` is created or anything is written (review-fix cycle 2,
  finding 1): if genuine unresolved MDX/JSX-shaped constructs remain
  anywhere in the preflight's output, the run aborts with a non-zero
  exit and ``--dest`` is never created, unless the operator passes the
  explicit ``--allow-unresolved-mdx`` override after reviewing the
  report's ``unresolved_constructs`` section. Only after this gate
  passes does the real write pass run, and the JSON report is written to
  ``--report`` only AFTER that write pass completes successfully.
  Dry-run is never gated by this check -- it only reports, so the
  operator can decide whether to override.
* This script never hardcodes or defaults to the operator's real external
  destination; ``--source`` and ``--dest`` are always explicit,
  operator-supplied arguments.
* Every file read is also resolved against, and verified to remain
  strictly inside, the original ``--source`` root
  (:func:`guard_read_path` / :class:`ContainmentViolation`, review-fix
  cycle 4): ``Path.is_file()``/``Path.rglob()`` follow symlinks
  transparently, so a symlinked leaf file -- or a symlinked ancestor
  directory, including an entire top-level product tree -- could
  otherwise cause a read from outside the operator-authorized corpus.
  This is a read-side fail-closed check, exactly mirroring the write-side
  ``guard_write_path`` / ``--dest`` guarantee above.
* Two different source files that would resolve to the SAME planned
  destination path (e.g. ``foo.mdx`` normalizing to ``foo.md`` while
  ``foo.md`` already exists in the same tree) are rejected as a
  :class:`DestinationCollisionError` (``EXIT_DEST_PATH_COLLISION``,
  review-fix cycle 4) during the read-only preflight, before ``--dest``
  is claimed. A ``--report`` path that resolves to any OTHER planned
  corpus output path (not just the reserved sentinel name) is similarly
  rejected (``EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT``, review-fix cycle
  4, finding qAsu) before ``--dest`` is claimed -- both checks use the
  same full, uncapped set of planned destination paths collected during
  the preflight pass.

EXACT OPERATOR COMMAND (documented per C.T2's acceptance criterion; this
command is never executed by an agent -- only the operator runs it):

    python scripts/hashicorp_mdx_normalize.py `
        --source "C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content" `
        --dest "C:\\Source\\Docs\\tf-unified-dev-docs-normalized" `
        --execute `
        --report "C:\\Source\\Docs\\tf-unified-dev-docs-normalized\\_normalize-report.json"

Omit ``--execute`` (and, if desired, point ``--report`` at any local
path) to preview the exact same plan with zero writes -- this is the
default mode and is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _hashicorp_mdx import normalize, selection  # noqa: E402

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_CONTAINMENT_VIOLATION = 3
EXIT_SOURCE_NOT_FOUND = 4
EXIT_DEST_ALREADY_EXISTS = 5
EXIT_UNRESOLVED_MDX_CONSTRUCTS = 6
EXIT_EXECUTION_FAILED = 7
EXIT_DEST_CLAIM_FAILED = 8
EXIT_REPORT_WRITE_FAILED = 9
EXIT_DEST_NOT_EMPTY = 10
EXIT_REPORT_PATH_RESERVED = 11
EXIT_DEST_PATH_COLLISION = 12
EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT = 13

#: Name of the exclusive claim sentinel file created directly under
#: ``--dest`` while an ``--execute`` run owns that destination (review-fix
#: cycle 3). An operator-chosen ``--report`` path CAN collide with this
#: reserved name (an independent review caught this after an earlier
#: version of this comment incorrectly claimed it could not): writing the
#: report there would overwrite the live sentinel, and the end-of-run
#: cleanup in :func:`main` would then delete the report it just wrote --
#: silently losing it while still returning success. ``main()`` rejects a
#: ``--report`` that resolves to exactly this reserved path under
#: ``--dest`` (``EXIT_REPORT_PATH_RESERVED``) before ``--dest`` is ever
#: claimed or written to.
CLAIM_SENTINEL_NAME = ".docline-hashicorp-mdx-normalize.claim"

#: Per-product cap on how many entries the dry-run/execute JSON plan's
#: ``planned_paths`` list records (C.T2 acceptance criterion: the plan must
#: include planned destination paths so an operator can audit exactly what
#: ``--execute`` would write; post-push Copilot review requested a bounded
#: representation so a real corpus with thousands of files per product
#: cannot balloon the report unboundedly). Exceeding the cap only truncates
#: the reported path *list* for that product -- it never affects the
#: authoritative ``file_counts`` totals or which files are actually
#: normalized/copied.
MAX_PLANNED_PATHS_PER_PRODUCT = 200

#: Image-like binary assets copied byte-for-byte, unchanged.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})
#: Ordinary Markdown files copied byte-for-byte, unchanged (no normalization needed).
ORDINARY_MD_EXTENSIONS = frozenset({".md", ".markdown"})
#: MDX files are normalized in-flight (read -> transform -> write .md).
MDX_EXTENSIONS = frozenset({".mdx"})
#: Everything else that is not a partial and not one of the extensions above
#: (PDFs, videos, JSON/YAML data files, etc.) is copied byte-for-byte too
#: (review-fix cycle 1, P2 finding) -- see ``generic_copied`` below. There is
#: deliberately no allow-list here: any suffix not already claimed by MDX/MD/
#: image handling falls through to the generic copy branch in
#: :func:`_process_one_product_tree`.


class ContainmentViolation(RuntimeError):
    """Raised when a resolved path -- read OR write -- falls outside its
    configured containment root (``--source`` for reads, ``--dest`` for
    writes)."""


class DestinationCollisionError(RuntimeError):
    """Raised when two different source files would resolve to the SAME
    planned destination path within a single ``--source`` -> ``--dest``
    run (review finding, Copilot review cycle 4) -- e.g. ``foo.mdx``
    normalizing to ``foo.md`` while ``foo.md`` already exists (or is
    separately planned) in the same tree. Detected during the read-only
    preflight, before ``--dest`` is ever claimed or written to: files are
    otherwise processed sequentially with no destination-path registry,
    so one source would silently overwrite the other's already-written
    output with no diagnostic."""


def guard_write_path(dest_root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and verify it falls strictly inside ``dest_root``.

    Returns the resolved candidate path on success. Raises
    :class:`ContainmentViolation` -- WITHOUT touching the filesystem --
    when the resolved candidate is not contained by ``dest_root``.

    CALLERS MUST WRITE USING THE RETURNED RESOLVED PATH, never the
    original ``candidate`` argument (review-fix cycle 2, finding 2): a
    caller that checks the resolved path here but later performs the
    actual write against the original, unresolved argument re-opens
    exactly the gap this guard exists to close. Callers that write at a
    meaningfully later point in the control flow should also call this
    function again immediately before that write, to narrow (not
    eliminate -- see below) the window between the check and the write.

    BEST-EFFORT CONTAINMENT, NOT A RACE-FREE GUARANTEE: ``Path.resolve()``
    is a plain filesystem read; nothing prevents a component of
    ``candidate`` from being replaced (e.g. a symlink retargeted, a
    directory swapped for a symlink) between the moment this function
    resolves and validates the path and the moment the caller actually
    opens the file for writing. Calling this function again right before
    the write narrows that TOCTOU window but cannot close it -- Python's
    standard library offers no atomic "open only if the fully-resolved
    path stays under this root" primitive. This guard is a fail-fast
    sanity check against operator/configuration error and ordinary
    non-adversarial races, not a hardened defense against a
    concurrently-adversarial filesystem.
    """
    dest_resolved = dest_root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(dest_resolved)
    except ValueError as exc:
        raise ContainmentViolation(
            f"refusing to write outside --dest: {candidate_resolved} is not under {dest_resolved}"
        ) from exc
    return candidate_resolved


def _reserved_sentinel_path(dest: Path) -> Path:
    """Return the fully-resolved path of the reserved claim sentinel under ``dest``.

    Used to reject an operator-chosen ``--report`` path that collides with
    this reserved name (independent-review finding, review-fix cycle 3):
    writing the report there would overwrite the live claim sentinel, and
    the end-of-run cleanup in :func:`main` would then delete the report it
    just wrote -- silently losing it while still returning success.
    """
    return dest.resolve() / CLAIM_SENTINEL_NAME


class DestClaimError(RuntimeError):
    """Base class for every way :func:`claim_destination` can fail to claim ``--dest``."""


class DestNotEmptyError(DestClaimError):
    """``--dest`` exists and contains content that is not a live claim of ours.

    Covers a pre-existing non-empty directory, a pre-existing non-directory
    path, and the (extremely narrow) window where something else appears
    under ``--dest`` between the emptiness check and the exclusive sentinel
    claim below.
    """


class DestAlreadyClaimedError(DestClaimError):
    """Another invocation already holds the exclusive claim sentinel for ``--dest``.

    Raised only when the sentinel file itself already exists at the moment
    this invocation attempts to create it exclusively -- i.e. two
    invocations genuinely raced for the same ``--dest`` and this one lost.
    """


class DestClaimFailedError(DestClaimError):
    """``--dest`` could not be claimed for a reason unrelated to pre-existing
    content or a concurrent claim (permission denial, a blocked ancestor
    path component, disk exhaustion, etc.)."""


def claim_destination(dest: Path) -> Path:
    """Atomically claim ``--dest`` for exclusive ``--execute`` use.

    Accepts an ABSENT ``--dest`` (created here) or an EXISTING ``--dest``
    that contains NO entries -- an existing, non-empty ``--dest`` (or one
    that exists as a non-directory) is rejected. Returns the claim sentinel
    :class:`~pathlib.Path` on success; the caller MUST remove exactly this
    sentinel (via :func:`release_destination_claim`) when the run finishes,
    whether it succeeds or fails, and must never remove anything else.

    MUTUAL EXCLUSION: the actual claim is an exclusive-create of a sentinel
    file directly under ``--dest`` (``os.O_CREAT | os.O_EXCL``), an
    OS-level atomic syscall. Of two invocations racing for the same
    ``--dest`` -- whether ``--dest`` was absent or already existed and
    empty for both -- exactly one wins the sentinel create and the other
    raises :class:`DestAlreadyClaimedError` instead of both proceeding to
    write. This is checked TWICE: once as a fast, non-atomic pre-check
    before attempting the claim (an existing ``--dest`` whose ONLY entry
    is exactly the reserved sentinel NAME is treated as "already claimed"
    and still proceeds to the authoritative O_EXCL attempt below rather
    than being rejected outright here; any OTHER pre-existing content
    rejects immediately as :class:`DestNotEmptyError`), and once again by
    re-listing ``--dest`` immediately after the sentinel is created,
    rejecting (and releasing our own sentinel) if anything besides the
    sentinel is present -- narrowing, without fully eliminating, the
    window in which a non-cooperating writer could drop content into
    ``--dest`` between the two checks.

    RESIDUAL RACE LIMITATIONS (documented accurately, not overstated): this
    guards against races BETWEEN COOPERATING INVOCATIONS OF THIS SAME
    SCRIPT racing for the same ``--dest`` -- it is not, and does not claim
    to be, protection against an arbitrary non-cooperating process writing
    into ``--dest`` at an arbitrary time (e.g. a file appearing after this
    function returns but before the write pass begins). As with
    :func:`guard_write_path`, this is a fail-fast sanity/mutual-exclusion
    check against ordinary, non-adversarial concurrency, not a hardened
    defense against a concurrently-adversarial filesystem.

    A stale sentinel left behind by a PRIOR run that crashed or was killed
    before it could remove its own sentinel is indistinguishable, on disk,
    from a genuinely live, in-progress claim: both look identical (a
    single file at the reserved sentinel name and nothing else), so both
    are reported the same way, as :class:`DestAlreadyClaimedError` --
    never auto-removed. If it truly is stale, the operator must inspect
    and remove it manually before retrying; this function never deletes
    anything it did not itself just create in THIS call. Any OTHER
    pre-existing content (with or without the sentinel alongside it) is
    reported distinctly as :class:`DestNotEmptyError`.
    """
    created_dest = False
    try:
        dest.mkdir(parents=True, exist_ok=False)
        created_dest = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise DestClaimFailedError(str(exc)) from exc

    if not created_dest:
        if not dest.is_dir():
            raise DestNotEmptyError(f"--dest exists and is not a directory: {dest}")
        try:
            existing_names = sorted(p.name for p in dest.iterdir())
        except OSError as exc:
            raise DestClaimFailedError(str(exc)) from exc
        if existing_names == [CLAIM_SENTINEL_NAME]:
            # The ONLY thing present is exactly our reserved claim sentinel
            # name -- this is a precise, recognizable signal that another
            # invocation is (or very recently was) actively claiming this
            # same --dest, distinct from ordinary leftover content. Report
            # it as such rather than a generic "not empty" rejection. The
            # O_EXCL create below still performs the actual, authoritative
            # mutual-exclusion check (this pre-check is advisory/fast-fail
            # only) -- if the other invocation released its claim in the
            # interim, the O_EXCL create below will succeed instead.
            pass
        elif existing_names:
            raise DestNotEmptyError(
                f"--dest already exists and is not empty: {dest} (contains "
                f"{len(existing_names)} pre-existing entr"
                f"{'y' if len(existing_names) == 1 else 'ies'}; a stale claim "
                "sentinel from a killed prior run looks identical to ordinary "
                "leftover content and is handled the same way -- inspect and "
                "remove it manually before retrying)"
            )

    sentinel = dest / CLAIM_SENTINEL_NAME
    try:
        fd = os.open(str(sentinel), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise DestAlreadyClaimedError(
            f"--dest is already claimed by another in-progress invocation: {dest} "
            f"(claim sentinel {sentinel.name} is already present)"
        ) from exc
    except OSError as exc:
        raise DestClaimFailedError(str(exc)) from exc

    try:
        os.close(fd)
    except OSError as exc:
        # The sentinel was physically created by the os.open() call above
        # (review-fix cycle 3, finding 2): if the close itself then fails,
        # release it here rather than leaving an orphaned sentinel on disk
        # that main() never learns about (this function never got to
        # return a sentinel path to its caller) and can therefore never
        # clean up -- every subsequent run against this --dest would
        # otherwise be permanently, silently blocked.
        release_destination_claim(sentinel)
        raise DestClaimFailedError(str(exc)) from exc

    try:
        post_claim_names = sorted(p.name for p in dest.iterdir())
    except OSError as exc:
        release_destination_claim(sentinel)
        raise DestClaimFailedError(str(exc)) from exc

    if post_claim_names != [CLAIM_SENTINEL_NAME]:
        release_destination_claim(sentinel)
        raise DestNotEmptyError(
            f"--dest gained unexpected content between the emptiness check and the "
            f"exclusive claim: {dest} -- rejecting rather than proceeding. This tool "
            "claims no protection against an arbitrary non-cooperating writer; only "
            "against races between cooperating invocations of this same script."
        )

    return sentinel


def release_destination_claim(sentinel: Path) -> None:
    """Best-effort removal of a claim sentinel created by THIS invocation's
    :func:`claim_destination` call.

    Removes ONLY the sentinel file itself -- never any other file under
    ``--dest``, and never ``--dest`` itself (partial output and the
    destination directory are always left in place, per the containment
    contract). Never raises: intended to run from a ``finally`` block, so
    a failure to remove the sentinel must never mask or replace the run's
    real exit code -- it is reported to stderr as a non-fatal warning
    instead.
    """
    try:
        sentinel.unlink()
    except OSError as exc:
        print(
            f"warning: failed to remove claim sentinel {sentinel} -- {exc}. If left "
            "behind, a future run against the same --dest will be rejected as "
            "not-empty until this sentinel is removed manually.",
            file=sys.stderr,
        )


def _is_partial_path(relative_path: Path) -> bool:
    """True if any path component is literally ``partials`` (case-insensitive).

    Partials/fragment files never carry frontmatter and must never be
    emitted as standalone documents, regardless of how deeply nested
    they are inside a selected product/version tree.
    """
    return any(part.lower() == "partials" for part in relative_path.parts)


@dataclass
class ProductCounts:
    mdx_normalized: int = 0
    md_copied: int = 0
    assets_copied: int = 0
    generic_copied: int = 0
    skipped_partials: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "mdx_normalized": self.mdx_normalized,
            "md_copied": self.md_copied,
            "assets_copied": self.assets_copied,
            "generic_copied": self.generic_copied,
            "skipped_partials": self.skipped_partials,
        }

    def add(self, other: ProductCounts) -> None:
        self.mdx_normalized += other.mdx_normalized
        self.md_copied += other.md_copied
        self.assets_copied += other.assets_copied
        self.generic_copied += other.generic_copied
        self.skipped_partials += other.skipped_partials


@dataclass
class ProductReport:
    versioned: bool
    selected_version: str | None
    counts: ProductCounts = field(default_factory=ProductCounts)
    #: Planned destination paths (posix-style, relative to ``--dest``) for
    #: every file this product will normalize/copy -- capped at
    #: ``MAX_PLANNED_PATHS_PER_PRODUCT`` entries; see
    #: ``planned_paths_truncated``. Skipped partials are never planned
    #: outputs and never appear here.
    planned_paths: list[str] = field(default_factory=list)
    #: True when this product had more write-eligible files than
    #: ``MAX_PLANNED_PATHS_PER_PRODUCT``, so ``planned_paths`` is a
    #: truncated prefix rather than the complete list. ``file_counts``
    #: above always remains the authoritative, untruncated totals.
    planned_paths_truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "versioned": self.versioned,
            "selected_version": self.selected_version,
            "file_counts": self.counts.as_dict(),
            "planned_paths": self.planned_paths,
            "planned_paths_truncated": self.planned_paths_truncated,
        }


@dataclass
class ReportBuilder:
    source: Path
    dest: Path
    execute: bool
    products: dict[str, ProductReport] = field(default_factory=dict)
    fallback_constructs: Counter[str] = field(default_factory=Counter)
    ambiguous_tokens: Counter[str] = field(default_factory=Counter)
    unresolved_constructs: Counter[str] = field(default_factory=Counter)
    excluded_top_level_dirs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    containment_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        totals = ProductCounts()
        for product_report in self.products.values():
            totals.add(product_report.counts)
        return {
            "schema_version": SCHEMA_VERSION,
            "source": str(self.source),
            "dest": str(self.dest),
            "execute": self.execute,
            "generated_at": datetime.now(UTC).isoformat(),
            "products": {name: pr.as_dict() for name, pr in sorted(self.products.items())},
            "totals": totals.as_dict(),
            "fallback_constructs": dict(sorted(self.fallback_constructs.items())),
            "ambiguous_tokens": dict(sorted(self.ambiguous_tokens.items())),
            "unresolved_constructs": dict(sorted(self.unresolved_constructs.items())),
            "excluded_top_level_dirs": sorted(self.excluded_top_level_dirs),
            "warnings": self.warnings,
            "containment_violations": self.containment_violations,
        }


def guard_read_path(source_root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and verify it falls strictly inside ``source_root``.

    Read-side counterpart to :func:`guard_write_path` (review finding,
    Copilot review cycle 4): ``Path.is_file()``/``Path.rglob()`` follow
    symlinks transparently, so a symlinked file -- or an ancestor
    directory that is itself a symlink, including an entire top-level
    product tree symlinked out from under ``--source`` -- could
    otherwise cause this tool to read content from outside the
    operator-authorized ``--source`` corpus without any indication in
    the report. ``Path.resolve()`` fully resolves every symlink in the
    chain, so checking the final resolved leaf-file path against the
    resolved ``source_root`` catches an escape introduced at ANY level
    (the file itself, a version directory, or the top-level product
    directory) with a single check.

    Returns the resolved candidate path on success. Raises
    :class:`ContainmentViolation` -- WITHOUT touching the filesystem
    beyond the read-only ``resolve()`` calls -- when the resolved
    candidate is not contained by ``source_root``. Callers must fail the
    run rather than silently skip: silently omitting an escaping file
    could hide the very tampering this guard is meant to surface.
    """
    source_resolved = source_root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(source_resolved)
    except ValueError as exc:
        raise ContainmentViolation(
            f"refusing to read outside --source: {candidate_resolved} is not under "
            f"{source_resolved} (symlink escape at {candidate})"
        ) from exc
    return candidate_resolved


def _iter_files_sorted(root: Path, source_root: Path) -> list[Path]:
    """Return every regular file under ``root``, sorted, after verifying
    (via :func:`guard_read_path`) that each one's fully-resolved path
    stays inside ``source_root``. Raises :class:`ContainmentViolation`
    the moment any escaping file is found, before any content is read.
    """
    if not root.is_dir():
        return []
    candidates = sorted(p for p in root.rglob("*") if p.is_file())
    for candidate in candidates:
        guard_read_path(source_root, candidate)
    return candidates


def _read_text_preserving_newlines(path: Path) -> str:
    """Read ``path`` as UTF-8 text with newline translation disabled.

    ``pathlib.Path.read_text()`` (on the Python 3.12 baseline this
    project targets) has no ``newline`` parameter and always performs
    universal-newline decoding, translating every ``\\r\\n``/``\\r`` to
    ``\\n`` -- silently discarding the source file's original
    line-ending convention before a single transform ever runs. Reading
    via ``open(..., newline="")`` instead disables that translation
    entirely, so the returned text carries the file's EXACT original
    bytes for line-ending purposes. This is required for frontmatter
    byte-for-byte preservation on Windows (review-fix cycle 4, finding
    p8Ph): :func:`normalize.normalize_mdx_to_md` splits this text into
    frontmatter (left completely untouched) and body (explicitly
    re-normalized to ``\\n`` for the transform pipeline), so only
    reading raw here lets the frontmatter's original bytes survive the
    whole round trip.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _process_one_product_tree(
    *,
    source_root: Path,
    product_root: Path,
    dest_product_root: Path,
    dest_root: Path,
    execute: bool,
    product_report: ProductReport,
    fallback_tally: Counter[str],
    ambiguous_tally: Counter[str],
    unresolved_tally: Counter[str],
    planned_dest_paths: set[str],
) -> None:
    """Streaming walk: for each file under ``product_root``, read -> (normalize) -> write.

    No bulk pre-copy or intermediate materialization occurs -- each file
    is handled individually, in one pass, whether or not ``execute`` is
    set. Only the final "write to disk" step is skipped when
    ``execute`` is ``False``.

    Every write-eligible file (MDX normalized, ordinary Markdown copied,
    an image asset, or a generic byte-for-byte copy) also records its
    planned destination path -- relative to ``dest_root``, posix-style --
    onto ``product_report.planned_paths``, capped at
    ``MAX_PLANNED_PATHS_PER_PRODUCT`` (C.T2 acceptance criterion: the
    dry-run/execute JSON plan must include planned destination paths so
    an operator can audit exactly what will be written). Skipped
    partials never get a planned path. Truncation only shortens the
    reported path list; it never affects ``product_report.counts``,
    which always remains the authoritative total.

    ``source_root`` is the overall ``--source`` corpus root (not just
    ``product_root``): every file discovered under ``product_root`` is
    validated by :func:`_iter_files_sorted` to resolve strictly inside
    ``source_root``, so a symlink escape is caught regardless of whether
    the offending symlink is the file itself, a version directory, or
    the top-level product directory.

    ``planned_dest_paths`` is an UNCAPPED set (shared across every
    product processed in this run, never truncated) of every planned
    destination path -- relative to ``dest_root``, posix-style -- claimed
    so far. Before a write-eligible file's destination is recorded, it is
    checked against this set (review finding p8PN, Copilot review cycle
    4): a second file mapping to an already-claimed destination (e.g.
    ``foo.mdx`` normalizing to ``foo.md`` while ``foo.md`` already exists
    in the same tree) raises :class:`DestinationCollisionError` instead
    of silently overwriting the earlier file's output. This check always
    runs, in both dry-run and ``--execute`` modes, before any write for
    the colliding file would occur.
    """
    counts = product_report.counts

    def _record_planned_path(dest_candidate: Path) -> None:
        dest_relative = dest_candidate.relative_to(dest_root).as_posix()
        if dest_relative in planned_dest_paths:
            raise DestinationCollisionError(
                f"planned destination path collision under --dest: '{dest_relative}' would "
                "be written by more than one source file -- refusing to proceed. This "
                "usually means an MDX file normalizes to the same name as an existing "
                "ordinary Markdown file in the same tree (e.g. foo.mdx -> foo.md colliding "
                "with an existing foo.md). Rename or remove one of the colliding source "
                "files to resolve this. Detected during the read-only preflight, before "
                "--dest was ever claimed or written to."
            )
        planned_dest_paths.add(dest_relative)
        if len(product_report.planned_paths) < MAX_PLANNED_PATHS_PER_PRODUCT:
            product_report.planned_paths.append(dest_relative)
        else:
            product_report.planned_paths_truncated = True

    for source_path in _iter_files_sorted(product_root, source_root):
        relative_path = source_path.relative_to(product_root)
        if _is_partial_path(relative_path):
            counts.skipped_partials += 1
            continue

        suffix = source_path.suffix.lower()
        if suffix in MDX_EXTENSIONS:
            text = _read_text_preserving_newlines(source_path)
            result = normalize.normalize_mdx_to_md(text)
            fallback_tally.update(result.fallback)
            ambiguous_tally.update(result.ambiguous)
            unresolved_tally.update(result.unresolved)
            counts.mdx_normalized += 1
            dest_relative = relative_path.with_suffix(".md")
            _record_planned_path(dest_product_root / dest_relative)
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / dest_relative)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                # newline="" mirrors the read side: the frontmatter
                # portion of result.text carries its ORIGINAL line-ending
                # bytes (preserved exactly by normalize_mdx_to_md), and
                # writing with translation disabled is what lets those
                # original bytes reach disk unchanged instead of being
                # re-mangled by write_text()'s default \n -> os.linesep
                # translation (review-fix cycle 4, finding p8Ph). The
                # body portion (always \n internally) is therefore also
                # written as literal \n rather than the platform's
                # newline convention -- a deliberate, documented
                # narrowing: only the frontmatter block is guaranteed
                # byte-for-byte; the body's own line-ending convention
                # was never separately guaranteed and is now simply LF
                # everywhere, regardless of host platform.
                dest_path.write_text(result.text, encoding="utf-8", newline="")
        elif suffix in ORDINARY_MD_EXTENSIONS:
            counts.md_copied += 1
            _record_planned_path(dest_product_root / relative_path)
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / relative_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, dest_path)
        elif suffix in IMAGE_EXTENSIONS:
            counts.assets_copied += 1
            _record_planned_path(dest_product_root / relative_path)
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / relative_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, dest_path)
        else:
            # Generic byte-for-byte copy (review-fix cycle 1, P2 finding):
            # any remaining non-partial, non-MDX file -- linked PDFs,
            # videos, JSON/YAML data files, and any other repository data
            # -- survives in the selected-tree output instead of being
            # silently dropped. There is no allow-list; only "partials"
            # and MDX get special treatment.
            counts.generic_copied += 1
            _record_planned_path(dest_product_root / relative_path)
            if execute:
                dest_path = guard_write_path(dest_root, dest_product_root / relative_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, dest_path)


def process_corpus(
    source: Path,
    dest: Path,
    execute: bool,
    planned_dest_paths: set[str] | None = None,
) -> dict[str, Any]:
    """Run the full selection + normalize-on-copy pipeline; return the JSON-able report dict.

    Shared by both dry-run and execute modes: the exact same selection
    and per-file read/normalize computation happens either way, so a
    dry-run's report is a faithful preview of what ``--execute`` would
    produce. Only the actual disk-write step is conditioned on
    ``execute``.

    ``planned_dest_paths``, when the caller supplies a set, is populated
    IN PLACE with every (uncapped) planned destination path -- relative
    to ``dest``, posix-style -- across the whole corpus. This lets a
    caller (see ``main()``'s ``--report`` collision check, review
    finding qAsu, Copilot review cycle 4) check an arbitrary candidate
    path against the FULL plan, unlike the per-product
    ``planned_paths`` list on each product's report entry, which is
    capped at ``MAX_PLANNED_PATHS_PER_PRODUCT`` for JSON-report-size
    reasons. When the caller omits this argument, an internal, discarded
    set is used instead -- duplicate-destination detection (review
    finding p8PN) always runs regardless of whether the caller wants the
    full set back.
    """
    if planned_dest_paths is None:
        planned_dest_paths = set()
    builder = ReportBuilder(source=source, dest=dest, execute=execute)

    top_level_dirs = sorted(p.name for p in source.iterdir() if p.is_dir())
    classification = selection.classify_products(top_level_dirs)

    for name in classification.excluded:
        builder.excluded_top_level_dirs.append(name)
        if name != "global":
            builder.warnings.append(
                f"Unrecognized top-level directory '{name}' -- not in the known "
                "product map; excluded from selection."
            )

    for product in classification.versioned:
        product_source_root = source / product
        version_dirnames = sorted(p.name for p in product_source_root.iterdir() if p.is_dir())
        selected = selection.select_latest_version(version_dirnames)
        product_report = ProductReport(versioned=True, selected_version=selected)
        builder.products[product] = product_report
        if selected is None:
            builder.warnings.append(
                f"Versioned product '{product}' has no valid version directories; skipped."
            )
            continue
        _process_one_product_tree(
            source_root=source,
            product_root=product_source_root / selected,
            dest_product_root=dest / product / selected,
            dest_root=dest,
            execute=execute,
            product_report=product_report,
            fallback_tally=builder.fallback_constructs,
            ambiguous_tally=builder.ambiguous_tokens,
            unresolved_tally=builder.unresolved_constructs,
            planned_dest_paths=planned_dest_paths,
        )

    for product in classification.unversioned:
        product_source_root = source / product
        product_report = ProductReport(versioned=False, selected_version=None)
        builder.products[product] = product_report
        _process_one_product_tree(
            source_root=source,
            product_root=product_source_root,
            dest_product_root=dest / product,
            dest_root=dest,
            execute=execute,
            product_report=product_report,
            fallback_tally=builder.fallback_constructs,
            ambiguous_tally=builder.ambiguous_tokens,
            unresolved_tally=builder.unresolved_constructs,
            planned_dest_paths=planned_dest_paths,
        )

    return builder.to_dict()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashicorp_mdx_normalize.py",
        description=(
            "Selectively copy the latest version of each versioned HashiCorp "
            "product (plus all unversioned products) from a read-only "
            "unified-docs corpus, converting .mdx to .md in-flight. Dry-run "
            "(zero writes) is the default; pass --execute to write."
        ),
        epilog=(
            "Exact operator command for the real external run (never executed "
            "by an agent):\n\n"
            "  python scripts/hashicorp_mdx_normalize.py "
            '--source "C:\\Source\\Docs\\hashicorp-tf-unified-dev-docs\\content" '
            '--dest "C:\\Source\\Docs\\tf-unified-dev-docs-normalized" '
            "--execute "
            '--report "C:\\Source\\Docs\\tf-unified-dev-docs-normalized'
            '\\_normalize-report.json"\n\n'
            "Omit --execute to preview the identical plan with zero writes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", required=True, type=Path, help="Read-only source corpus root")
    parser.add_argument(
        "--dest", required=True, type=Path, help="Destination root for normalized output"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help=(
            "Actually write output (default: dry-run, zero writes). Accepts "
            "--dest that is ABSENT or EMPTY -- never a pre-existing non-empty "
            "destination. --dest is claimed exclusively via a sentinel file "
            "immediately before writes begin; execute mode never deletes, "
            "replaces, or overlays pre-existing content."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=(
            "Optional path to also persist the JSON report (always printed to "
            "stdout regardless). In --execute mode, this path MUST resolve "
            "inside --dest (guarded the same way as every other write) or the "
            "process fails closed before any corpus write begins. In dry-run "
            "mode this flag is accepted but never written to disk -- dry-run "
            "performs zero writes, full stop."
        ),
    )
    parser.add_argument(
        "--allow-unresolved-mdx",
        action="store_true",
        default=False,
        help=(
            "Explicit operator override: proceed with --execute even when "
            "genuine unresolved MDX/JSX-shaped components remain after "
            "normalization (see the report's 'unresolved_constructs' section). "
            "Without this flag, --execute fails closed (non-zero exit) when any "
            "unresolved construct remains anywhere in the corpus. Dry-run is "
            "never affected by this flag -- it only reports."
        ),
    )
    return parser


def _dest_precheck(dest: Path) -> str | None:
    """Return an error message if ``dest`` is not in an execute-claimable
    state, else ``None``.

    Execute mode accepts ``dest`` ABSENT or EXISTING-AND-EMPTY (review-fix
    cycle 3): a pre-existing, empty directory is a legitimate claim target,
    since the destination is claimed via an exclusive sentinel file rather
    than via the directory's own creation. This cheap, early,
    non-authoritative check exists only to fail fast with a clear message
    in the common (non-racing) case; the actual concurrency-safe claim is
    :func:`claim_destination`, called immediately before any corpus write
    begins, which re-verifies emptiness right before -- and again
    immediately after -- atomically creating the claim sentinel.

    A ``dest`` whose ONLY entry is exactly the reserved claim sentinel name
    is deliberately NOT rejected here (review-fix cycle 3, finding 1): that
    state means another invocation is genuinely still claiming -- or very
    recently claimed -- this same ``--dest``, and only
    :func:`claim_destination` can distinguish that live-claim case from
    ordinary stale content and report the specific, documented exit code
    for it. Rejecting it at this earlier, cheaper check would silently
    collapse that distinction for the realistic staggered-rerun case (a
    second invocation started sometime after a first already claimed
    ``--dest`` but is still writing) -- not just an infinitesimal timing
    window -- which is exactly the scenario this precheck's own sentinel
    awareness must not defeat. An ``OSError`` while inspecting an existing
    ``--dest`` is deferred the same way: this cheap check never guesses at
    an exit code for a filesystem-level failure it cannot fully diagnose --
    :func:`claim_destination` performs the same enumeration under its own
    authoritative error handling and maps any such failure to
    ``EXIT_DEST_CLAIM_FAILED`` with a clear message.
    """
    if not dest.exists():
        return None
    if not dest.is_dir():
        return f"--dest exists and is not a directory: {dest}"
    try:
        existing_names = sorted(p.name for p in dest.iterdir())
    except OSError:
        return None
    if existing_names and existing_names != [CLAIM_SENTINEL_NAME]:
        return (
            f"--dest already exists and is not empty: {dest} -- execute mode accepts an "
            "ABSENT --dest or an EXISTING, EMPTY --dest; it is claimed exclusively via a "
            "sentinel file immediately before writes begin. Execute mode never deletes, "
            "replaces, or overlays pre-existing content -- point --execute at a path that "
            "is absent or empty."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    source: Path = args.source
    dest: Path = args.dest

    if not source.is_dir():
        print(f"error: --source is not a directory: {source}", file=sys.stderr)
        return EXIT_SOURCE_NOT_FOUND

    if not args.execute:
        # Dry run: a single read-only pass, zero writes, ever -- process_corpus
        # never touches the filesystem for writes when execute is False.
        try:
            report = process_corpus(source=source, dest=dest, execute=False)
        except ContainmentViolation as exc:
            print(f"error: containment violation: {exc}", file=sys.stderr)
            return EXIT_CONTAINMENT_VIOLATION
        except DestinationCollisionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_DEST_PATH_COLLISION

        print(json.dumps(report, indent=2, sort_keys=True))
        if args.report is not None:
            print(
                "note: --report is ignored in dry-run mode (zero-write contract) -- "
                "the plan is only printed to stdout. Pass --execute to also persist "
                "the report file (guarded under --dest).",
                file=sys.stderr,
            )
        return EXIT_OK

    # ---------------------------------------------------------------
    # --execute mode: every gate below MUST run, in this order, BEFORE
    # --dest is created/claimed or a single byte is written anywhere
    # (review-fix cycle 2, finding 1). A rejected run at any of these
    # gates leaves --dest untouched (absent, or existing-and-empty exactly
    # as found) and never touches --report.
    # ---------------------------------------------------------------

    dest_error = _dest_precheck(dest)
    if dest_error is not None:
        print(f"error: {dest_error}", file=sys.stderr)
        return EXIT_DEST_NOT_EMPTY

    if args.report is not None:
        try:
            resolved_report_precheck = guard_write_path(dest, args.report)
        except ContainmentViolation as exc:
            print(f"error: containment violation: {exc}", file=sys.stderr)
            return EXIT_CONTAINMENT_VIOLATION
        if resolved_report_precheck == _reserved_sentinel_path(dest):
            print(
                f"error: --report resolves to the reserved claim sentinel path: "
                f"{resolved_report_precheck} -- choose a different --report path. Writing "
                "here would overwrite the live claim sentinel, and it would then be deleted "
                "when the claim is released at the end of this run, silently losing the "
                "report. --dest was never created or claimed.",
                file=sys.stderr,
            )
            return EXIT_REPORT_PATH_RESERVED

    # Complete READ-ONLY normalization preflight: the SAME selection and
    # per-file normalization logic as the real write pass below, but
    # with execute=False so process_corpus is guaranteed to perform zero
    # writes. This is the only way to inspect unresolved_constructs
    # before anything is written -- the alternative (checking the report
    # only after execute writes have already happened) is exactly the
    # cycle-2 finding-1 bug this preflight fixes. ``planned_dest_paths``
    # collects the FULL, uncapped set of planned destination paths so the
    # --report collision check below (finding qAsu) can consult it, and
    # duplicate-destination detection (finding p8PN) runs as a side
    # effect of the preflight call itself.
    planned_dest_paths: set[str] = set()
    try:
        preflight_report = process_corpus(
            source=source, dest=dest, execute=False, planned_dest_paths=planned_dest_paths
        )
    except ContainmentViolation as exc:
        print(f"error: containment violation: {exc}", file=sys.stderr)
        return EXIT_CONTAINMENT_VIOLATION
    except DestinationCollisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DEST_PATH_COLLISION

    if args.report is not None:
        dest_resolved_for_report_check = dest.resolve()
        try:
            report_relative_to_dest = resolved_report_precheck.relative_to(
                dest_resolved_for_report_check
            ).as_posix()
        except ValueError:
            report_relative_to_dest = None
        if report_relative_to_dest is not None and report_relative_to_dest in planned_dest_paths:
            print(
                f"error: --report resolves to a planned corpus output path: "
                f"{resolved_report_precheck} -- choose a different --report path. Writing "
                "the report there would silently replace a successfully normalized/copied "
                "document with the JSON report. --dest was never created or claimed.",
                file=sys.stderr,
            )
            return EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT

    if preflight_report["unresolved_constructs"] and not args.allow_unresolved_mdx:
        unresolved_summary = ", ".join(
            f"{name}={count}"
            for name, count in sorted(preflight_report["unresolved_constructs"].items())
        )
        print(
            "error: genuine unresolved MDX/JSX components remain after normalization: "
            f"{unresolved_summary}. Review the report's 'unresolved_constructs' section; "
            "pass --allow-unresolved-mdx to proceed anyway once reviewed. This is a "
            "read-only preflight check -- --dest was never created and nothing was "
            "written.",
            file=sys.stderr,
        )
        return EXIT_UNRESOLVED_MDX_CONSTRUCTS

    # Atomic claim of --dest -- the FIRST filesystem mutation in this
    # entire invocation on the common path where --dest's own parent
    # directory already exists (if intermediate ancestors are missing,
    # ``parents=True`` creates them first via ordinary, non-atomic
    # ``mkdir`` calls -- see the module docstring's containment-contract
    # bullet). --dest may be ABSENT or an EXISTING, EMPTY directory
    # (review-fix cycle 3); either way the claim itself is an exclusive
    # sentinel-file create directly under --dest, so of two invocations
    # racing for the same --dest exactly one succeeds and the other fails
    # closed instead of both silently interleaving output. The sentinel
    # this invocation creates is removed when this run finishes -- success
    # or failure -- but --dest itself, and any partial or complete
    # corpus/report output, is never touched by that cleanup.
    try:
        claim_sentinel = claim_destination(dest)
    except DestNotEmptyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DEST_NOT_EMPTY
    except DestAlreadyClaimedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DEST_ALREADY_EXISTS
    except DestClaimFailedError as exc:
        print(
            f"error: failed to claim --dest: {dest} -- {exc}. No corpus output was "
            "written; this failure occurred before any write began.",
            file=sys.stderr,
        )
        return EXIT_DEST_CLAIM_FAILED

    try:
        # The real write pass: identical selection/normalization logic as the
        # preflight above, this time actually writing to disk.
        try:
            report = process_corpus(source=source, dest=dest, execute=True)
        except ContainmentViolation as exc:
            print(
                f"error: containment violation: {exc} -- PARTIAL OUTPUT MAY ALREADY HAVE BEEN "
                f"WRITTEN under {dest} before this failure. It is left in place (never "
                "auto-deleted); inspect and remove it manually before retrying.",
                file=sys.stderr,
            )
            return EXIT_CONTAINMENT_VIOLATION
        except DestinationCollisionError as exc:
            print(
                f"error: {exc} PARTIAL OUTPUT MAY ALREADY HAVE BEEN WRITTEN under {dest} "
                "before this failure. It is left in place (never auto-deleted); inspect and "
                "remove it manually before retrying.",
                file=sys.stderr,
            )
            return EXIT_DEST_PATH_COLLISION
        except OSError as exc:
            print(
                f"error: execution failed partway through writing output: {exc}. PARTIAL "
                f"OUTPUT HAS BEEN LEFT IN PLACE under {dest} (never auto-deleted) -- inspect "
                "and remove it manually before retrying.",
                file=sys.stderr,
            )
            return EXIT_EXECUTION_FAILED

        payload = json.dumps(report, indent=2, sort_keys=True)
        print(payload)

        # The report is written ONLY after the write pass above completed
        # successfully (review-fix cycle 2, finding 1). Re-guard immediately
        # before writing (finding 2) and write through the RESOLVED path
        # this call returns -- never the original, possibly-unresolved
        # args.report -- so the write always targets what was just verified,
        # not a stale resolution computed earlier in the run.
        if args.report is not None:
            try:
                resolved_report = guard_write_path(dest, args.report)
            except ContainmentViolation as exc:
                print(
                    f"error: containment violation writing report: {exc}. Corpus output "
                    f"under {dest} was already written successfully and is left in place; "
                    "only the report file was rejected.",
                    file=sys.stderr,
                )
                return EXIT_CONTAINMENT_VIOLATION
            if resolved_report == _reserved_sentinel_path(dest):
                # Defense-in-depth only: the early precheck above already
                # rejects this collision before --dest is claimed on the
                # ordinary path. This duplicate check exists for the same
                # reason guard_write_path itself is re-invoked here rather
                # than trusted from the earlier call (review-fix cycle 2,
                # finding 2) -- to narrow, not assume away, the window in
                # which the resolved report path could differ between the
                # two checks.
                print(
                    f"error: --report resolves to the reserved claim sentinel path: "
                    f"{resolved_report} -- choose a different --report path. Corpus output "
                    f"under {dest} was already written successfully and is left in place; "
                    "only the report file was rejected. Writing here would overwrite the "
                    "live claim sentinel, and it would then be deleted when the claim is "
                    "released at the end of this run, silently losing the report.",
                    file=sys.stderr,
                )
                return EXIT_REPORT_PATH_RESERVED
            try:
                report_relative_to_dest_final = resolved_report.relative_to(
                    dest.resolve()
                ).as_posix()
            except ValueError:
                report_relative_to_dest_final = None
            if (
                report_relative_to_dest_final is not None
                and report_relative_to_dest_final in planned_dest_paths
            ):
                # Defense-in-depth only, same rationale as the reserved-
                # sentinel re-check immediately above: the early
                # precheck/preflight already rejects this collision before
                # --dest is claimed on the ordinary path.
                print(
                    f"error: --report resolves to a planned corpus output path: "
                    f"{resolved_report} -- choose a different --report path. Corpus output "
                    f"under {dest} was already written successfully and is left in place; "
                    "only the report file was rejected. Writing here would silently replace "
                    "a normalized/copied document with the JSON report.",
                    file=sys.stderr,
                )
                return EXIT_REPORT_PATH_COLLIDES_WITH_OUTPUT
            try:
                resolved_report.parent.mkdir(parents=True, exist_ok=True)
                resolved_report.write_text(payload, encoding="utf-8")
            except OSError as exc:
                print(
                    f"error: failed to write --report: {resolved_report} -- {exc}. Corpus "
                    f"output under {dest} was already written successfully and is left in "
                    "place; only the report file failed to write.",
                    file=sys.stderr,
                )
                return EXIT_REPORT_WRITE_FAILED

        if report["unresolved_constructs"] and not args.allow_unresolved_mdx:
            # Defense-in-depth only: the preflight gate above already aborted
            # before any write if unresolved constructs were present. This
            # remains reachable only if --source mutates between the
            # preflight and write passes (a scenario this tool does not
            # otherwise guard against), so it is intentionally kept as a
            # belt-and-suspenders check rather than assumed unreachable.
            unresolved_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(report["unresolved_constructs"].items())
            )
            print(
                "error: genuine unresolved MDX/JSX components remain after normalization: "
                f"{unresolved_summary}. Review the report's 'unresolved_constructs' section; "
                "pass --allow-unresolved-mdx to proceed anyway once reviewed.",
                file=sys.stderr,
            )
            return EXIT_UNRESOLVED_MDX_CONSTRUCTS

        return EXIT_OK
    finally:
        # Runs on EVERY exit from this block -- normal return, an early
        # return on a failure branch above, or an uncaught exception.
        # Removes ONLY the sentinel this invocation created; --dest and any
        # partial or complete output are always left exactly as they were.
        release_destination_claim(claim_sentinel)


if __name__ == "__main__":
    raise SystemExit(main())
