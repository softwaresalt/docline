#!/usr/bin/env bash
# Releases an advisory file lock for agent concurrency control.
# Deletes the .{filename}.lock file created by acquire_lock.sh.
# If the lock file does not exist, emits a warning but exits successfully.
#
# Usage: scripts/release_lock.sh <filepath>

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: release_lock.sh <filepath>" >&2
    exit 1
fi

FILEPATH="$1"

if [ ! -e "$FILEPATH" ]; then
    echo "Warning: Target file does not exist: $FILEPATH" >&2
fi

TARGET_DIR="$(dirname "$FILEPATH")"
if [ -d "$TARGET_DIR" ]; then
    RESOLVED_DIR="$(cd "$TARGET_DIR" && pwd -P)"
else
    echo "Error: Parent directory does not exist: $TARGET_DIR" >&2
    exit 1
fi

FILENAME="$(basename "$FILEPATH")"
LOCKFILE="${RESOLVED_DIR}/.${FILENAME}.lock"

if [ ! -e "$LOCKFILE" ]; then
    echo "Warning: No lock file found for: $FILEPATH (already released or never locked)" >&2
    exit 0
fi

if rm -f "$LOCKFILE"; then
    echo "Lock released: $LOCKFILE"
    exit 0
else
    echo "Error: Failed to remove lock file: $LOCKFILE" >&2
    exit 1
fi
