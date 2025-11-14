# Conversation Search - Technical Reference

## Complete Command Reference

### claude-finder init

Initialize the database and perform initial indexing.

```bash
claude-finder init [--days DAYS] [--no-summarize] [--force]
```

**Options:**
- `--days DAYS`: Index last N days of conversations (default: 7)
- `--no-summarize`: Skip AI summarization, use truncation (faster)
- `--force`: Reinitialize existing database

**What it does:**
1. Creates `~/.claude-finder/index.db` SQLite database
2. Scans `~/.claude/projects/` for conversation files
3. Parses JSONL conversation format
4. Generates AI summaries using Claude Haiku (via `claude` CLI)
5. Builds FTS5 search index

**Example:**
```bash
# Initialize with last 30 days
claude-finder init --days 30

# Quick init without AI summaries
claude-finder init --no-summarize
```

---

### claude-finder search

Search conversations using full-text search on AI-generated summaries.

```bash
claude-finder search QUERY [--days DAYS] [--project PROJECT] [--limit LIMIT] [--content] [--json]
```

**Arguments:**
- `QUERY`: Search query (supports FTS5 syntax)

**Options:**
- `--days DAYS`: Limit to last N days
- `--project PROJECT`: Filter by project path
- `--limit LIMIT`: Max results (default: 20)
- `--content`: Show full message content instead of summaries
- `--json`: Output as JSON

**Search Syntax:**
- Simple: `authentication bug`
- Multiple terms: `react hooks useEffect` (implicit AND)
- Phrases: `"exact phrase"`
- Operators: `auth AND bug`, `react OR vue`

**Examples:**
```bash
# Basic search
claude-finder search "authentication"

# Time-scoped search
claude-finder search "database" --days 30

# Project-specific search
claude-finder search "api" --project /home/user/myapp

# Get JSON output (for programmatic use)
claude-finder search "hooks" --json
```

---

### claude-finder context

Get conversation context around a specific message.

```bash
claude-finder context MESSAGE_UUID [--depth DEPTH] [--content] [--json]
```

**Arguments:**
- `MESSAGE_UUID`: Message UUID from search results

**Options:**
- `--depth DEPTH`: How many parent levels to show (default: 3)
- `--content`: Show full content instead of summaries
- `--json`: Output as JSON

**What it returns:**
- Parent messages (conversation history leading to this message)
- Target message
- Child messages (responses to this message)

**Example:**
```bash
# Get context for a message
claude-finder context abc-123-def --depth 5

# With full content
claude-finder context abc-123-def --content --json
```

---

### claude-finder list

List recent conversations.

```bash
claude-finder list [--days DAYS] [--limit LIMIT] [--json]
```

**Options:**
- `--days DAYS`: Show conversations from last N days (default: 7)
- `--limit LIMIT`: Max conversations to show (default: 20)
- `--json`: Output as JSON

**Example:**
```bash
# List last week's conversations
claude-finder list --days 7

# List last 50 conversations
claude-finder list --limit 50 --json
```

---

### claude-finder tree

Show the conversation tree structure for a session.

```bash
claude-finder tree SESSION_ID [--json]
```

**Arguments:**
- `SESSION_ID`: Session ID from list or search results

**Options:**
- `--json`: Output as JSON

**Use case:** Visualize conversation branching and checkpoint structure.

**Example:**
```bash
claude-finder tree session-abc-123
```

---

### claude-finder index

Re-index conversations (useful for catching up after tool updates).

```bash
claude-finder index [--days DAYS] [--all] [--no-summarize]
```

**Options:**
- `--days DAYS`: Index last N days (default: 1)
- `--all`: Index all conversations
- `--no-summarize`: Skip AI summarization

**Example:**
```bash
# Reindex last 7 days
claude-finder index --days 7

# Reindex everything
claude-finder index --all
```

---

### claude-finder watch

Start file watcher daemon for real-time indexing.

```bash
claude-finder watch [--verbose]
```

**Options:**
- `--verbose`: Print file change events

**What it does:**
1. Monitors `~/.claude/projects/` for file changes
2. Waits 30 seconds after last change (idle threshold)
3. Re-indexes modified conversations
4. Runs batch AI summarization on new messages

**Usage:**
Run in a separate terminal or tmux/screen session:
```bash
# In tmux
tmux new -s claude-watcher
claude-finder watch
# Detach: Ctrl+B, D

# Later, reattach
tmux attach -t claude-watcher
```

---

## Database Schema

**Location:** `~/.claude-finder/index.db`

**Tables:**
- `messages`: Individual messages with summaries and tree structure
- `conversations`: Session metadata and summaries
- `message_summaries_fts`: FTS5 full-text search index
- `index_queue`: Processing queue (internal use)

**Key Fields:**
- `message_uuid`: Unique message identifier
- `parent_uuid`: Parent message (tree structure)
- `session_id`: Conversation session
- `summary`: AI-generated 1-2 sentence summary
- `full_content`: Original message content
- `is_summarized`: Has AI summary (vs truncation)

---

## How Summarization Works

1. **Batch Processing**: Messages are grouped in batches of 20
2. **Claude Haiku**: Uses `claude` CLI in headless mode
3. **Prompt**: "Summarize this message in 1-2 sentences"
4. **Noise Filtering**: Filters out tool spam and system messages
5. **Fallback**: If API unavailable, uses smart truncation

**Requirements:**
- `claude` CLI must be installed and available in PATH
- Anthropic API key configured (via `claude` login)

---

## JSON Output Format

All commands support `--json` for structured output.

**Search results:**
```json
[
  {
    "message_uuid": "abc-123",
    "timestamp": "2025-01-13T10:30:00",
    "message_type": "user",
    "summary": "User asks about authentication bug",
    "project_path": "/home/user/projects/myapp",
    "conversation_summary": "Auth Bug Fix",
    "session_id": "session-xyz",
    "depth": 3,
    "is_sidechain": false
  }
]
```

**Context results:**
```json
{
  "message": { /* target message */ },
  "parents": [ /* ancestor messages */ ],
  "children": [ /* responses */ ]
}
```

---

## Performance Tips

1. **Use `--days` to scope searches** - Faster and more relevant
2. **Start with summaries** - Only use `--content` when needed
3. **Run watcher for freshness** - Keeps index up-to-date
4. **Periodic reindexing** - `claude-finder index --days 30` weekly
5. **Project filtering** - Use `--project` for focused searches

---

## Integration with Claude Code

This Skill is designed to work with Claude Code's conversation format:

**Conversation File Format (JSONL):**
```jsonl
{"type": "summary", "leafUuid": "...", "conversationSummary": "..."}
{"uuid": "msg-1", "type": "user", "message": {...}, "timestamp": "..."}
{"uuid": "msg-2", "type": "assistant", "message": {...}, "parentUuid": "msg-1"}
```

**Key Features:**
- Preserves tree structure (branches, checkpoints)
- Filters tool noise automatically
- Handles multi-project setups
- Concurrent-safe with SQLite WAL mode

---

## Troubleshooting

**Import errors after installation:**
- Ensure using Python 3.9+
- Try: `uv tool uninstall claude-finder && uv tool install claude-finder`

**Search returns no results:**
- Check if database exists: `ls ~/.claude-finder/index.db`
- Reindex: `claude-finder index --days 30`
- Verify conversations exist: `ls ~/.claude/projects/`

**Watcher not processing changes:**
- Check DB permissions
- Verify `~/.claude/projects/` path
- Look for errors in watcher output

**Slow summarization:**
- Use `--no-summarize` for faster indexing
- Check Claude CLI authentication: `claude --version`
- Haiku API rate limits may apply

---

## Advanced Usage

**Custom database path:**
```python
from claude_finder.core.indexer import ConversationIndexer
indexer = ConversationIndexer(db_path="/custom/path/index.db")
```

**Programmatic search:**
```python
from claude_finder.core.search import ConversationSearch
search = ConversationSearch()
results = search.search_conversations("query", days_back=7)
for r in results:
    print(r['summary'])
```

**Batch operations:**
```bash
# Export all conversations about "database"
claude-finder search "database" --json > database_convs.json

# Reindex specific time range
for days in 7 14 30; do
    claude-finder index --days $days
done
```
