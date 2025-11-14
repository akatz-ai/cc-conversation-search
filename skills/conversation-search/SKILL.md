---
name: conversation-search
description: Find and resume Claude Code conversations by searching message summaries. Returns session IDs and project paths for easy resumption via 'claude --resume'. Use when user asks "find that conversation about X", "what did we discuss about Y", or wants to locate and return to past work.
allowed-tools: Bash
---

# Conversation Search

Find past conversations in your Claude Code history and get the commands to resume them.

## Prerequisites & Auto-Installation

The skill requires the `cc-conversation-search` CLI tool (v0.4.0+ minimum).

**IMPORTANT: Always upgrade to latest when skill activates**

```bash
# Check if installed
if command -v cc-conversation-search &> /dev/null; then
    # Already installed - upgrade to latest to match plugin version
    uv tool upgrade cc-conversation-search 2>/dev/null || pip install --upgrade cc-conversation-search
    echo "Upgraded to: $(cc-conversation-search --version)"
else
    echo "Not installed - installing now..."
fi
```

**If not installed:**

### Automatic Installation

```bash
# Try uv first (preferred), fallback to pip
if command -v uv &> /dev/null; then
    uv tool install cc-conversation-search
else
    pip install --user cc-conversation-search
    export PATH="$HOME/.local/bin:$PATH"
fi

# Initialize database
cc-conversation-search init --days 7
```

**If installation fails**, guide the user:
```
The conversation-search plugin requires the cc-conversation-search CLI tool.

Install it manually:
  uv tool install cc-conversation-search  (recommended)
  OR
  pip install --user cc-conversation-search

Then initialize:
  cc-conversation-search init
```

**After installation, verify:**
```bash
cc-conversation-search --version  # Should show 0.4.0 or higher
```

**Do not attempt search** until installation is confirmed.

### Version Compatibility Note

Minimum CLI version: 0.4.0 (required for --version, --quiet, proper error messages).

**Best practice**: This skill automatically upgrades the CLI tool on every activation to ensure compatibility with plugin updates.

## Query Type Classification

**CRITICAL: Before searching, identify the query type:**

### Type 1: Temporal Queries
User asks about time ("yesterday", "last week", "today's work"):
- **Use:** `--date`, `--since`, or `--until` parameters
- **Examples:**
  - "What did we work on yesterday?" → `--date yesterday`
  - "Summarize this week" → `--since` (7 days ago)
  - "Today's conversations" → `--date today`

### Type 2: Topic Queries
User asks about content ("auth bug", "Redis"):
- **Use:** `search "topic"` with optional time scope
- **Examples:**
  - "Find Redis conversation" → `search "Redis"`
  - "Recent auth work" → `search "auth" --days 7`

### Type 3: Hybrid Queries
User asks about topic + time:
- **Use:** Combine search query with date filters
- **Examples:**
  - "Find yesterday's auth discussion" → `search "auth" --date yesterday`
  - "Redis work from last week" → `search "Redis" --since` (week ago)

## Progressive Search Workflow

Use this tiered approach, escalating only if needed:

**Copy this checklist:**
```
Search Progress:
- [ ] Level 0: Classify query type (temporal/topic/hybrid)
- [ ] Level 1: Simple focused search (fast, auto-indexes)
- [ ] Level 2: Broader search without filters
- [ ] Level 3: Manual exploration (token-heavy)
- [ ] Level 4: Present results
```

### Level 1: Simple Search (Start Here)

**Note**: Search automatically indexes recent conversations, so you always get fresh data.

Run focused search with time scope:
```bash
cc-conversation-search search "query terms" --days 14 --json
```

Parse JSON. **If clear matches** → skip to Level 4.

### Level 2: Broader Search

If Level 1 yields no good matches:
- Remove time filter: `cc-conversation-search search "query" --json`
- Try alternative keywords (e.g., "auth" vs "authentication")
- Try broader terms (e.g., "database" vs "postgres migration")

**If matches found** → skip to Level 4.

### Level 3: Manual Exploration (Token-Heavy)

Only escalate here if Levels 1-2 failed:

1. List recent conversations:
   ```bash
   cc-conversation-search list --days 30 --json
   ```

2. Read conversation summaries from JSON to identify promising ones

3. Get conversation tree for promising sessions:
   ```bash
   cc-conversation-search tree <SESSION_ID> --json
   ```

4. Manually read message summaries in tree to find relevant content

**If match found** → proceed to Level 4.

### Level 4: Present Results

**If found:**

Display session resumption information using this markdown format:

**Session Details**

- **Session**: abc-123-session-id
- **Project**: /home/user/projects/myproject
- **Time**: 2025-11-13 22:50
- **Message**: def-456-message-uuid

**To Resume This Conversation**

```bash
cd /home/user/projects/myproject
claude --resume abc-123-session-id
```

Optionally offer context expansion:
```bash
cc-conversation-search context <UUID> --json
```

**If not found after all 3 levels:**
- State clearly: "No matching conversations found after exhaustive search"
- Suggest: `cc-conversation-search index --days 90` to reindex older history
- Acknowledge: "The conversation may not exist or may be older than indexed range"

## Error Handling

**Tool not installed:**
```bash
which cc-conversation-search
```
If not found:
1. Install: `uv tool install cc-conversation-search` or `pip install cc-conversation-search`
2. Initialize: `cc-conversation-search init`
3. **Do not proceed** until confirmed installed

Note: The package name and command are both `cc-conversation-search`

**Database not found:**
User must run: `cc-conversation-search init`
Creates `~/.conversation-search/index.db` and indexes last 7 days.

**No results at Level 1 or 2:**
Escalate to Level 3. **Do not give up early.**

**No results after Level 3:**
Only then report "no match" with reindexing suggestion.

## Command Reference

### Search Command
```bash
# Topic search with time scope
cc-conversation-search search "query" --days N --json

# Search by calendar date
cc-conversation-search search "query" --date yesterday --json
cc-conversation-search search "query" --date today --json
cc-conversation-search search "query" --date 2025-11-13 --json

# Search by date range
cc-conversation-search search "query" --since yesterday --until today --json
cc-conversation-search search "query" --since 2025-11-10 --until 2025-11-13 --json

# All time (no date filter)
cc-conversation-search search "query" --json
```

**Date Filter Options:**
- `--days N`: Last N days from NOW (e.g., --days 7 = last 7 days)
- `--date DATE`: Specific calendar day (midnight to midnight)
- `--since DATE`: From date onwards (inclusive)
- `--until DATE`: Up to and including date
- DATE formats: `yyyy-mm-dd`, `yesterday`, `today`

**Important:** Cannot mix `--days` with `--date/--since/--until`

### List Conversations
```bash
# List by calendar date
cc-conversation-search list --date yesterday --json
cc-conversation-search list --date today --json

# List by range
cc-conversation-search list --since yesterday --until today --json

# List last N days (relative to NOW)
cc-conversation-search list --days 7 --json
```

### Context Expansion
```bash
cc-conversation-search context <UUID> --json
cc-conversation-search context <UUID> --no-index --json  # Skip indexing
```

**Conversation tree:**
```bash
cc-conversation-search tree <SESSION_ID> --json
```

**Resume helper** (returns copy-pasteable commands):
```bash
cc-conversation-search resume <UUID>
```

**Always use `--json`** for structured output in search/context/list/tree.

See [REFERENCE.md](REFERENCE.md) for complete command documentation.

## Examples

**Example 1: User wants to find specific discussion**
```
User: "Find that conversation where we fixed the authentication bug"
```

You should:
1. Run Level 1: `cc-conversation-search search "authentication bug" --days 14 --json`
2. If no matches, Level 2: `cc-conversation-search search "auth" --json`
3. If still no matches, Level 3 (list + tree exploration)
4. When found, display session ID, project path, timestamp, and resume commands

**Example 2: User exploring past work**
```
User: "Did we ever discuss React hooks?"
```

You should:
1. Run Level 1: `cc-conversation-search search "react hooks" --days 30 --json`
2. Display all matches with session IDs and project paths
3. Show resume commands for each match

**Example 3: User wants to return to specific work**
```
User: "I want to go back to where we started implementing the API"
```

You should:
1. Search: `cc-conversation-search search "implementing API" --json`
2. Display session ID and project path prominently
3. Show exact resume commands
4. Offer context if needed: `cc-conversation-search context <UUID> --json`

**Example 4: User asks about yesterday (temporal query)**
```
User: "What did we work on yesterday?"
```

You should:
1. Classify: TEMPORAL query (not topic search)
2. Run: `cc-conversation-search list --date yesterday --json`
3. Parse JSON results
4. Group by project_path
5. Analyze conversation_summary fields
6. Present organized summary by project with highlights

**Example 5: User wants this week's summary (temporal query)**
```
User: "Summarize what we accomplished this week"
```

You should:
1. Classify: TEMPORAL query
2. Calculate date range (7 days ago to today)
3. Run: `cc-conversation-search list --since <7-days-ago> --until today --json`
4. Parse all conversations from last 7 days
5. Group by project_path and date
6. Present weekly summary organized by project

**Example 6: User wants recent work on specific topic (hybrid)**
```
User: "Show me yesterday's authentication work"
```

You should:
1. Classify: HYBRID (topic + time)
2. Run: `cc-conversation-search search "authentication" --date yesterday --json`
3. Display matching sessions with resume commands
