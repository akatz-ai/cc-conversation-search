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

## Progressive Search Workflow

Use this tiered approach, escalating only if needed:

**Copy this checklist:**
```
Search Progress:
- [ ] Level 0: JIT Index (always run first, now instant!)
- [ ] Level 1: Simple focused search (fast)
- [ ] Level 2: Broader search without filters
- [ ] Level 3: Manual exploration (token-heavy)
- [ ] Level 4: Present results
```

### Level 0: JIT Indexing (ALWAYS RUN FIRST)

**IMPORTANT**: Always run index before search to ensure fresh data:
```bash
cc-conversation-search index --days 7 --quiet
```

This is instant (no AI calls) and ensures you're searching the latest conversations. Use --quiet for minimal output.

### Level 1: Simple Search (Start Here)

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

Display session resumption information in this order:

```
Session: abc-123-session-id
Project: /home/user/projects/myproject
Time: 2025-11-13 22:50
Message: def-456-message-uuid

To resume:
  cd /home/user/projects/myproject
  claude --resume abc-123-session-id
```

Include:
- **Session ID** (required for resumption)
- **Project path** (cd there first)
- **Timestamp** (verify it's the right one)
- **Message UUID** (for context retrieval if needed)
- **Copy-pasteable commands** (cd + claude --resume)

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

**Search:**
```bash
cc-conversation-search search "query" --days N --json
cc-conversation-search search "query" --json  # All time
```

**Context expansion:**
```bash
cc-conversation-search context <UUID> --json
```

**List conversations:**
```bash
cc-conversation-search list --days 30 --json
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
1. Run Level 0 (JIT index): `cc-conversation-search index --days 7 --quiet`
2. Run Level 1: `cc-conversation-search search "authentication bug" --days 14 --json`
3. If no matches, Level 2: `cc-conversation-search search "auth" --json`
4. If still no matches, Level 3 (list + tree exploration)
5. When found, display session ID, project path, timestamp, and resume commands

**Example 2: User exploring past work**
```
User: "Did we ever discuss React hooks?"
```

You should:
1. Run Level 0 (JIT index): `cc-conversation-search index --days 7 --quiet`
2. Run Level 1: `cc-conversation-search search "react hooks" --days 30 --json`
3. Display all matches with session IDs and project paths
4. Show resume commands for each match

**Example 3: User wants to return to specific work**
```
User: "I want to go back to where we started implementing the API"
```

You should:
1. Run Level 0 (JIT index): `cc-conversation-search index --days 7 --quiet`
2. Search: `cc-conversation-search search "implementing API" --json`
3. Display session ID and project path prominently
4. Show exact resume commands
5. Offer context if needed: `cc-conversation-search context <UUID> --json`
