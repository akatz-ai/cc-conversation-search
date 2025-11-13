#!/bin/bash
# Claude Code Hook: Index new messages after each conversation exchange
# Install: ln -s $(pwd)/hooks/post-message.sh ~/.claude/hooks/user-prompt-submit.sh

set -e

# Path to the claude-finder installation
CLAUDE_FINDER_DIR="${CLAUDE_FINDER_DIR:-$(dirname $(dirname $(readlink -f $0)))}"
VENV_PYTHON="$CLAUDE_FINDER_DIR/venv/bin/python3"
INDEXER="$CLAUDE_FINDER_DIR/src/indexer.py"
LOCK_FILE="$HOME/.claude-finder/indexer.lock"

# Use system python if venv doesn't exist
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

# Only run indexing periodically (every 10th message) to avoid overhead
# Use a simple counter file
COUNTER_FILE="$HOME/.claude-finder/message_counter"
mkdir -p "$(dirname $COUNTER_FILE)"

# Read and increment counter
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE")
else
    COUNT=0
fi

COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

# Only index every 10th message to reduce overhead
if [ $((COUNT % 10)) -ne 0 ]; then
    exit 0
fi

# Check if indexer is already running
if [ -f "$LOCK_FILE" ]; then
    # Check if the process is actually running
    if ps -p $(cat "$LOCK_FILE") > /dev/null 2>&1; then
        # Indexer already running, skip
        exit 0
    else
        # Stale lock file, remove it
        rm "$LOCK_FILE"
    fi
fi

# Run indexer in background (non-blocking)
(
    echo $$ > "$LOCK_FILE"
    trap "rm -f $LOCK_FILE" EXIT

    # Strategy: First ensure messages are indexed (without summaries)
    # Then call Haiku agent to add summaries to recent messages

    # Step 1: Quick index without summaries (fast)
    "$VENV_PYTHON" "$INDEXER" --days 1 --no-summarize > /dev/null 2>&1

    # Step 2: Use Haiku agent to summarize last 10 messages from current conversation
    # Get the most recent conversation file
    PROJECTS_DIR="$HOME/.claude/projects"
    CURRENT_PROJECT=$(echo "$PWD" | sed 's|/|-|g')
    CURRENT_CONV_DIR="$PROJECTS_DIR/$CURRENT_PROJECT"

    if [ -d "$CURRENT_CONV_DIR" ]; then
        LATEST_CONV=$(ls -t "$CURRENT_CONV_DIR"/*.jsonl 2>/dev/null | grep -v 'agent-' | head -1)

        if [ -n "$LATEST_CONV" ]; then
            SUMMARIZER="$CLAUDE_FINDER_DIR/src/summarize_and_index.py"
            "$VENV_PYTHON" "$SUMMARIZER" "$LATEST_CONV" 10 > /dev/null 2>&1
        fi
    fi

) &

# Detach from parent process
disown

exit 0
