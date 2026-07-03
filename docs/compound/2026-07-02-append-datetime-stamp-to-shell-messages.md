---
date: 2026-07-02
category: append-datetime-stamp-to-shell-messages
keywords: [datetime, timestamp, output, copilot-cli, shell, message, convention, traceability, Get-Date]
confidence: high
evidence: Operator directive 2026-07-02 during 044-S post-merge closure — end every message written to the Copilot shell with a datetime stamp
---

# Append a datetime stamp to the end of every message written to the Copilot shell

## Convention

Whenever the agent writes a message out to the GitHub Copilot CLI (shell), it
MUST append a datetime stamp as the last line of the output. This gives every
agent turn an explicit, traceable time marker in the terminal transcript.

## How

* Prefer the `<current_datetime>` value the environment supplies on a user turn.
* When no `<current_datetime>` is present (or an accurate wall-clock reading is
  needed after long-running work), read the real time with PowerShell:

  ```powershell
  Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"
  ```

* Emit the stamp on its own final line, e.g. `2026-07-02T11:16:46-07:00`.

## Rule

* End-of-message datetime stamp is required, not optional.
* Use ISO-8601 with the local UTC offset for unambiguous ordering.
* Do not fabricate a time — derive it from the supplied `<current_datetime>` or
  a real `Get-Date` reading.
