#!/usr/bin/env bash
# Index new conversations when a Claude Code session ends.
# This keeps the search index fresh without a manual search first.
# The task is local and fast. It makes no network calls.

set -eu

# Opt out: set CC_CONVERSATION_SEARCH_NO_AUTOINDEX to any value.
if [ -n "${CC_CONVERSATION_SEARCH_NO_AUTOINDEX:-}" ]; then
  exit 0
fi

# Find the CLI. Prefer PATH. Fall back to the uv/pip user path.
if command -v cc-conversation-search >/dev/null 2>&1; then
  cmd="cc-conversation-search"
elif [ -x "$HOME/.local/bin/cc-conversation-search" ]; then
  cmd="$HOME/.local/bin/cc-conversation-search"
else
  # The CLI is not installed. Do nothing.
  exit 0
fi

# Index recent conversations. Stay silent. Never block the session exit.
"$cmd" index --quiet >/dev/null 2>&1 || true
