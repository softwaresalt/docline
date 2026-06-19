---
date: 2026-06-19
shipment: 034-S
category: backlogit-dependency-persistence
keywords: [backlogit, add_dependency, dependencies, frontmatter, sync_index, item_deps, persistence]
confidence: high
evidence: 034-S Ship session — add_dependency edges for 032.003-T vanished after backlogit_sync_index (v1.2.0)
---

# backlogit_add_dependency does not persist to markdown — encode dependencies in frontmatter

## Problem

`backlogit_add_dependency(item_id, depends_on)` writes the edge only to the
disposable SQLite `item_deps` cache in backlogit v1.2.0. It does **not** write
the `dependencies:` field into the artifact's markdown frontmatter, and it does
not bump the file's `updated_at`. Because the markdown files are the source of
truth and the SQLite index is rebuilt from them, every dependency added this way
is **erased by the next `backlogit_sync_index`** (or any rehydration).

This contradicts `backlogit-yaml-header-tooling.instructions.md`, which claims
`add_dependency` "Manages the item_deps table **and frontmatter `dependencies`
field**." In v1.2.0 the frontmatter half is not implemented.

## Symptom

```
add_dependency(032.003-T -> 032.001-T)   # status: added
get_dependencies(032.003-T)              # [edge present]
sync_index()                             # rehydrate from markdown
get_dependencies(032.003-T)              # null  <-- edge gone
```

## Fix

Encode the dependency directly in the artifact's frontmatter as a YAML list, in
alphabetical key position (after `custom_fields:`, before `id:`):

```yaml
dependencies:
    - 032.001-T
    - 032.002-T
```

Then run `backlogit_sync_index` and re-verify with `get_dependencies` — the
edges now survive rehydration because they live in the git-tracked source.
`backlogit_create_item` also accepts a `dependencies` param that writes the
frontmatter correctly; prefer that at creation time.

## Rule

- Treat `add_dependency` as a cache-only convenience. For any dependency that
  must survive a sync (i.e. all real dependencies), write the `dependencies:`
  frontmatter list directly or set it via `create_item`.
- Always re-verify dependency edges with one `sync_index` + `get_dependencies`
  round-trip before trusting them.
