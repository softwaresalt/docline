---
description: "Backlog tool integration instructions — teaches agents how to interact with the installed backlog management tool using abstracted operations"
applyTo: '**'
---

# Backlog Integration Instructions

This workspace uses **backlogit** for structured backlog management. All agents MUST use the backlog tool for task tracking rather than creating ad-hoc markdown files or static task lists.

## Tool Configuration

| Setting | Value |
|---------|-------|
| Tool | backlogit |
| Directory | `.backlogit/` |
| Access | MCP + CLI |
| Registry | `.autoharness/backlog-registry.yaml` |

## Operation Reference

Use these operations for all backlog interactions. The operation names are abstract — the actual tool names and parameters are mapped through the backlog registry.

### Core Operations (All Tools)

| Operation | MCP Tool | CLI Command | Purpose |
|-----------|----------|-------------|---------|
| Create task | `backlogit_create_item` | `backlogit add` | Create a new task/artifact |
| List tasks | `backlogit_list_items` | `backlogit list` | List tasks with filters |
| Get task | `backlogit_get_item` | `backlogit get {id}` | Retrieve task details |
| Update task | `backlogit_update_item` | `backlogit update {id}` | Modify task fields |
| Move task | `backlogit_move_item` | `backlogit move {id} {status}` | Change task status |
| Search | `backlogit_search_items` | `backlogit search {query}` | Full-text search |
| Complete | `backlogit_move_item` | `backlogit move {id} --status done` | Mark task complete |

### Status Values

| Abstract Status | Tool-Specific Value |
|----------------|---------------------|
| Queued | `queued` |
| Active | `active` |
| Done | `done` |
| Blocked | `blocked` |

### Extended Operations (Tool-Dependent)

| Operation | MCP Tool | Purpose |
|---|---|---|
| SQL query | `backlogit_query_sql` | Run read-only SQL against the backlog index for targeted inspection |
| Save memory | `backlogit_save_memory` | Persist concise agent memory or handoff summaries |
| Create checkpoint | `backlogit_create_checkpoint` | Save structured session state for later recovery |
| List checkpoints | `backlogit_list_checkpoints` | Inspect active or recent checkpoints |
| Track commit | `backlogit_track_commit` | Associate a commit SHA with an artifact for traceability |
| Create shipment | `backlogit_create_shipment` | Create a shipment artifact for grouped delivery |
| Stash intake | `backlogit_stash` | Add deferred work to the stash with kind and priority |
| Harvest stash | `backlogit_harvest_stash` | Promote stash items into backlog artifacts |
| Deliberate | `backlogit_deliberate` | Create a structured deliberation linked to a stash entry |
| Add semantic link | `backlogit_add_link` | Record informational relationships such as `related_to` or `duplicate_of` |
| Add dependency | `backlogit_add_dependency` | Encode execution-blocking relationships between artifacts |

## Agent Workflow Patterns

### Creating a Task

```text
Call backlogit_create_item with:
  title: "Task title"
  artifact_type: "task"
  status: "queued"
  description: "Task description"
  parent_id: "parent-task-id"  (if applicable)
  labels: "label1,label2"      (if applicable)
```

### Claiming a Task (Status → Active)

```text
Call backlogit_move_item with:
  id: "task-id"
  status: "active"
```

### Completing a Task

```text
Call backlogit_move_item with:
  id: "task-id"
```

### Listing Ready Tasks

```text
Call backlogit_list_items with:
  status: "queued"
```

### Adding a Label

```text
Call backlogit_update_item with:
  id: "task-id"
  labels: "existing-label,harness-ready"
```

## Advanced Patterns When Supported

If the registry advertises advanced features, prefer them over ad hoc workarounds:

* **Token-efficient lookup** — use the query operation when `features.sql_query` is true
* **Ready-work selection** — use queue-aware operations when `features.queue` is true
* **Dependency reasoning** — use dependency operations when `features.dependencies` is true
* **Agent continuity** — use memory and checkpoint operations when `features.memory` or `features.checkpoints` are true
* **Traceability** — use comment or commit-tracking operations when `features.comments` or `features.commit_tracking` are true
* **Index freshness** — use sync / rehydration operations when the workspace was edited outside normal mutation tools

If a tool-specific overlay instruction file is installed (for example,
`.github/instructions/backlogit.instructions.md`), follow it in addition to this generic guide.

## Rules

1. **Always use the backlog tool** for task management. Do not create markdown task files outside the `.backlogit/` directory.
2. **Use abstract status values** mapped through the registry, not hardcoded strings.
3. **Check the registry** (`.autoharness/backlog-registry.yaml`) for the exact field names and operation parameters when unsure.
4. **Prefer MCP tools** over CLI when both are available — MCP returns structured JSON, CLI returns human-readable text.
5. **Feature gating**: Before calling an extended operation, verify the feature is supported by checking the `features` section in the registry.

Generated by autoharness | Template: backlog-integration.instructions.md.tmpl
