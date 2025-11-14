# Conversation Search

Find and resume past Claude Code conversations using smart hybrid extraction and JIT indexing. Get session IDs and project paths to easily jump back into previous work.

## Features

- **Session Resumption**: Get exact commands to resume past conversations
- **Unified CLI**: Single `cc-conversation-search` command with intuitive subcommands
- **Calendar Date Filtering**: Intuitive `--date yesterday`, `--since`, `--until` parameters
- **Smart Extraction**: Hybrid indexing (full user content + smart assistant extraction)
- **JIT Indexing**: Instant indexing before search (no AI calls, no delays)
- **Local Timezone Display**: All timestamps shown in your local time
- **Meta-Conversation Filtering**: Automatically excludes search tool usage from results
- **Progressive Exploration**: Simple search → broader search → manual exploration
- **Conversation Context**: Expand context incrementally around any message
- **Claude Code Skill**: Integrated Skill that outputs session resumption commands
- **Multi-Project Support**: Works across all your Claude Code projects

## Quick Start

### Installation via Claude Code Plugin (Recommended)

Install the complete plugin (skill + CLI tool instructions) directly in Claude Code:

```bash
# Add this repo's marketplace
/plugin marketplace add akatz-ai/cc-conversation-search

# Install the plugin
/plugin install conversation-search
```

Then follow the installation instructions shown by Claude to:
1. Install the CLI tool: `uv tool install cc-conversation-search`
2. Initialize the database: `cc-conversation-search init`

### Manual Installation

#### 1. Install CLI Tool

```bash
# Using uv (recommended)
uv tool install cc-conversation-search

# Or using pip
pip install cc-conversation-search
```

#### 2. Initialize Database

```bash
cc-conversation-search init
```

This creates the database and indexes your last 7 days of conversations.

#### 3. Install Skill (Optional)

```bash
mkdir -p ~/.claude/skills/conversation-search
cp skills/conversation-search/* ~/.claude/skills/conversation-search/
```

### Basic Usage

```bash
# Search for conversations (shows session ID and resume commands)
cc-conversation-search search "authentication bug"

# Search with calendar date filters
cc-conversation-search search "react hooks" --date yesterday
cc-conversation-search search "auth" --since 2025-11-10 --until 2025-11-13

# List conversations by date
cc-conversation-search list --date yesterday
cc-conversation-search list --since "2025-11-01"

# Traditional relative time filters still work
cc-conversation-search search "query" --days 30

# Get resume commands for a specific message
cc-conversation-search resume <MESSAGE_UUID>

# Use with uvx (no install needed)
uvx cc-conversation-search search "query"
```

### Using with Claude Code Skill

Once installed, ask Claude:

**Topic-based queries:**
- "Find that conversation where we discussed authentication"
- "Locate the conversation about React hooks"
- "What did we talk about regarding the database?"

**Temporal queries (NEW in v0.4.8):**
- "What did we work on yesterday?"
- "Summarize today's conversations"
- "Show me this week's work"

**Hybrid queries:**
- "Find yesterday's authentication work"
- "Show recent Redis discussions"

**Auto-Installation**: If the CLI tool isn't installed, the skill will automatically attempt to install it via `uv` or `pip`, then initialize the database. In most cases, everything "just works" after installing the plugin!

Claude will show you the session ID, project path, and exact commands to resume the conversation.

## Command Reference

### `cc-conversation-search init`
Initialize database and perform initial indexing
```bash
cc-conversation-search init [--days 7] [--no-extract] [--force]
```

### `cc-conversation-search index`
JIT index conversations (instant, no AI calls)
```bash
cc-conversation-search index [--days N] [--all] [--no-extract]
```

**IMPORTANT**: The skill always runs `index` before `search` for fresh data.

### `cc-conversation-search search`
Search conversations with flexible date filtering
```bash
# Traditional relative time
cc-conversation-search search "query" [--days N] [--project PATH] [--content] [--json]

# Calendar date filtering (v0.4.8+)
cc-conversation-search search "query" --date yesterday [--json]
cc-conversation-search search "query" --date 2025-11-13 [--json]
cc-conversation-search search "query" --since 2025-11-10 --until 2025-11-13 [--json]

# Date formats: YYYY-MM-DD, "yesterday", "today"
# Note: --days cannot be combined with --date/--since/--until
```

### `cc-conversation-search context`
Get context around a specific message
```bash
cc-conversation-search context MESSAGE_UUID [--depth 5] [--content] [--json]
```

### `cc-conversation-search list`
List recent conversations with calendar date support
```bash
# Traditional relative time
cc-conversation-search list [--days 7] [--limit 20] [--json]

# Calendar date filtering (v0.4.8+)
cc-conversation-search list --date yesterday [--json]
cc-conversation-search list --since 2025-11-10 --until today [--json]
```

### `cc-conversation-search tree`
View conversation tree structure
```bash
cc-conversation-search tree SESSION_ID [--json]
```

## Architecture

```
~/.claude/
├── projects/           # Claude Code conversation files (JSONL)
│   └── {project}/
│       └── {session}.jsonl
└── skills/
    └── conversation-search/  # Optional Skill

~/.conversation-search/
└── index.db           # SQLite database with indexed conversations
```

**Key Purpose**: Find session IDs and project paths to resume past conversations.

### Database Schema

- **messages**: Individual messages with summaries, tree structure (parent_uuid), timestamps
- **conversations**: Session metadata with conversation summaries
- **message_summaries_fts**: FTS5 full-text search index
- **index_queue**: Processing queue for batch operations

## How It Works

1. **Indexer**: Scans `~/.claude/projects/` for JSONL conversation files, parses tree structure
2. **Smart Extraction**: Hybrid approach - full user content + first 500/last 200 chars for assistant
3. **Meta-Conversation Filtering**: Automatically detects and excludes conversations where Claude used the search tool (prevents search results pollution)
4. **Search**: FTS5 full-text search over extracted content with conversation tree traversal
5. **Calendar Date Filtering**: Intuitive date parameters (`--date yesterday`) using SQLite date functions
6. **JIT Indexing**: Skill runs `index` before `search` for fresh data (instant, no AI calls)
7. **Local Timezone Display**: All timestamps converted to your local timezone for readability

## Claude Code Skill

The included Skill allows Claude to search your conversation history automatically.

**Example usage:**

**Topic-based query:**
```
User: "Find that conversation where we started implementing the API"
Claude: [Activates conversation-search Skill]
        [Classifies as Topic query]
        [Runs: cc-conversation-search search "implementing API" --days 14 --json]
        [Finds match]
        [Displays session ID, project path, and resume commands]

        Output:
        Session: abc-123-session-id
        Project: /home/user/projects/myproject
        Time: 2025-11-13 22:50 (local time)

        To resume:
          cd /home/user/projects/myproject
          claude --resume abc-123-session-id
```

**Temporal query (NEW in v0.4.8):**
```
User: "What did we work on yesterday?"
Claude: [Activates conversation-search Skill]
        [Classifies as Temporal query]
        [Runs: cc-conversation-search list --date yesterday --json]
        [Analyzes conversations by project]

        Output:
        Yesterday's work summary:

        Project: /home/user/projects/api-service
        - Implemented Redis caching layer
        - Fixed authentication timeout bug
        Session: def-456-session-id

        Project: /home/user/projects/frontend
        - Updated React components for new API
        Session: ghi-789-session-id
```

See `skills/conversation-search/SKILL.md` for progressive search workflow and complete documentation.

## Advanced Usage

### JSON Output for Scripting

All commands support `--json` flag:
```bash
# Export search results
cc-conversation-search search "authentication" --json > auth_convs.json

# Programmatic processing
cc-conversation-search list --days 30 --json | jq '.[] | .conversation_summary'
```

### Programmatic Use

```python
from conversation_search.core.search import ConversationSearch
from conversation_search.core.indexer import ConversationIndexer

# Search for messages with calendar date filtering
search = ConversationSearch()

# Traditional relative time
results = search.search_conversations("authentication", days_back=7)

# New calendar date filtering (v0.4.8+)
results = search.search_conversations("authentication", date="yesterday")
results = search.search_conversations("auth", since="2025-11-10", until="2025-11-13")

for r in results:
    print(f"{r['message_uuid']}: {r['summary']}")

# List conversations by date
convs = search.list_recent_conversations(date="yesterday")
convs = search.list_recent_conversations(since="2025-11-10", until="today")

# Index conversations
indexer = ConversationIndexer()
indexer.index_all(days_back=7)
indexer.close()
```

## Configuration

**Database location:** `~/.conversation-search/index.db`

**No configuration file needed** - all settings via command-line flags.

## Performance

- **Smart Extraction**: Instant (no AI calls), deterministic
- **Indexing Speed**: ~1000+ messages/second (no API latency)
- **Storage**: ~1-2KB per message (extracted text + metadata)
- **Search Speed**: SQLite FTS5 is very fast, even with 100K+ messages
- **Cost**: $0 (no AI API calls during indexing)

## Development

### Setup

```bash
git clone https://github.com/akatz-ai/cc-conversation-search
cd cc-conversation-search
uv tool install -e .
```

### Run Tests

```bash
pytest tests/
```

### Project Structure

```
conversation-search/
├── src/
│   └── conversation_search/
│       ├── __init__.py
│       ├── cli.py              # Unified CLI
│       ├── core/
│       │   ├── indexer.py      # Conversation indexing + meta-filtering
│       │   ├── search.py       # Search functionality + date filtering
│       │   ├── date_utils.py   # Calendar date parsing (v0.4.8+)
│       │   └── summarization.py # Smart hybrid extraction
│       └── data/
│           └── schema.sql      # Database schema
├── skills/
│   └── conversation-search/
│       ├── SKILL.md           # Claude Code Skill with query classification
│       └── REFERENCE.md       # Complete command reference
├── tests/
│   ├── test_date_utils.py     # Date parsing tests
│   ├── test_date_filtering.py # Date filter integration tests
│   └── test_search_pair_detection.py # Meta-filtering tests
├── pyproject.toml
└── README.md
```

## Troubleshooting

**"Database not found" error:**
```bash
cc-conversation-search init
```

**"No conversations found":**
- Verify `~/.claude/projects/` exists and contains JSONL files
- Use Claude Code to create some conversations first

**Want to skip extraction and use raw content only:**
```bash
# Store only raw content (even faster, but less optimized for search)
cc-conversation-search init --no-extract
```

**Skill not activating:**
- Check Skill location: `ls ~/.claude/skills/conversation-search/SKILL.md`
- Verify YAML frontmatter format
- Restart Claude Code
- Try explicit trigger: "Search my conversations for X"

**Import errors:**
```bash
uv tool uninstall cc-conversation-search
uv tool install cc-conversation-search
```

## Contributing

PRs welcome! This is an experimental tool to improve Claude Code workflow.

### Areas for Contribution

- Vector embeddings for semantic similarity search
- Web UI for conversation tree visualization
- Export conversation branches as markdown
- Conversation analytics (topics, frequency, etc.)
- Additional Claude Code Skills using the search API

## License

MIT

## Acknowledgments

Built for the Claude Code ecosystem. Uses smart hybrid extraction for instant, cost-free indexing.
