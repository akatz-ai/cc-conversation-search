# Claude Finder

A powerful conversation indexing and search system for Claude Code that enables semantic search across your entire conversation history with progressive disclosure.

## Features

- **Unified CLI**: Single `claude-finder` command with intuitive subcommands
- **Automatic Indexing**: Indexes conversations from `~/.claude/projects` with AI-generated summaries
- **Semantic Search**: Full-text search across Haiku-generated message summaries
- **Conversation Context**: Progressive disclosure - expand context incrementally as needed
- **Real-time Updates**: Optional file watcher for automatic indexing
- **Claude Code Skill**: Integrated Skill for Claude to search conversation history
- **Multi-Project Support**: Works across all your Claude Code projects

## Quick Start

### Installation

```bash
# Using uv (recommended)
uv tool install claude-finder

# Or using pip
pip install claude-finder
```

### Initialize

```bash
claude-finder init
```

This creates the database and indexes your last 7 days of conversations.

### Search

```bash
# Search for conversations
claude-finder search "authentication bug"

# Search with time filter
claude-finder search "react hooks" --days 30

# Get full content
claude-finder search "database migration" --content
```

### Install Claude Code Skill (Optional)

For Claude to automatically search your conversation history:

```bash
# Personal Skill
mkdir -p ~/.claude/skills/conversation-search
cp skill/SKILL.md ~/.claude/skills/conversation-search/
cp skill/REFERENCE.md ~/.claude/skills/conversation-search/

# Now ask Claude: "What did we discuss about authentication?"
```

## Command Reference

### `claude-finder init`
Initialize database and perform initial indexing
```bash
claude-finder init [--days 7] [--no-summarize] [--force]
```

### `claude-finder search`
Search conversations
```bash
claude-finder search "query" [--days N] [--project PATH] [--content] [--json]
```

### `claude-finder context`
Get context around a specific message
```bash
claude-finder context MESSAGE_UUID [--depth 5] [--content] [--json]
```

### `claude-finder list`
List recent conversations
```bash
claude-finder list [--days 7] [--limit 20] [--json]
```

### `claude-finder tree`
View conversation tree structure
```bash
claude-finder tree SESSION_ID [--json]
```

### `claude-finder index`
Re-index conversations
```bash
claude-finder index [--days N] [--all] [--no-summarize]
```

### `claude-finder watch`
Start file watcher for real-time indexing
```bash
claude-finder watch [--verbose]
```

## Architecture

```
~/.claude/
├── projects/           # Claude Code conversation files (JSONL)
│   └── {project}/
│       └── {session}.jsonl
└── skills/
    └── conversation-search/  # Optional Skill

~/.claude-finder/
├── index.db           # SQLite database with indexed conversations
└── watcher.log        # Optional watcher logs
```

### Database Schema

- **messages**: Individual messages with summaries, tree structure (parent_uuid), timestamps
- **conversations**: Session metadata with conversation summaries
- **message_summaries_fts**: FTS5 full-text search index
- **index_queue**: Processing queue for batch operations

## How It Works

1. **Indexer**: Scans `~/.claude/projects/` for JSONL conversation files, parses tree structure
2. **Summarizer**: Calls Claude Haiku via `claude` CLI to generate 1-2 sentence summaries
3. **Search**: FTS5 semantic search over summaries with conversation tree traversal
4. **Watcher**: Optional daemon that monitors file changes and updates index in real-time

## Claude Code Skill

The included Skill allows Claude to search your conversation history automatically.

**Example usage:**
```
User: "What did we discuss about React hooks last week?"
Claude: [Activates conversation-search Skill]
        [Runs: claude-finder search "react hooks" --days 7 --json]
        [Presents results with context]
```

See `skill/SKILL.md` for complete Skill documentation.

## Advanced Usage

### Real-time Indexing with Watcher

Run in a separate terminal or tmux:
```bash
claude-finder watch
```

The watcher:
- Monitors `~/.claude/projects/` for changes
- Waits 30 seconds after last change (idle threshold)
- Re-indexes modified conversations
- Runs batch AI summarization on new messages

### JSON Output for Scripting

All commands support `--json` flag:
```bash
# Export search results
claude-finder search "authentication" --json > auth_convs.json

# Programmatic processing
claude-finder list --days 30 --json | jq '.[] | .conversation_summary'
```

### Programmatic Use

```python
from claude_finder.core.search import ConversationSearch
from claude_finder.core.indexer import ConversationIndexer

# Search
search = ConversationSearch()
results = search.search_conversations("authentication", days_back=7)
for r in results:
    print(f"{r['timestamp']}: {r['summary']}")

# Index
indexer = ConversationIndexer()
indexer.scan_and_index(days_back=7)
indexer.close()
```

## Configuration

**Database location:** `~/.claude-finder/index.db`

**No configuration file needed** - all settings via command-line flags.

## Performance

- **Summarization**: Uses Haiku for fast, cheap summaries (~1-2 sentences per message)
- **Indexing Speed**: ~10-50 messages/second (depends on Haiku API latency)
- **Storage**: ~1-2KB per message (summary + metadata)
- **Search Speed**: SQLite FTS5 is very fast, even with 100K+ messages

## Development

### Setup

```bash
git clone https://github.com/yourusername/claude-finder
cd claude-finder
uv tool install -e .
```

### Run Tests

```bash
pytest tests/
```

### Project Structure

```
claude-finder/
├── src/
│   └── claude_finder/
│       ├── __init__.py
│       ├── cli.py              # Unified CLI
│       ├── core/
│       │   ├── indexer.py      # Conversation indexing
│       │   ├── search.py       # Search functionality
│       │   ├── summarization.py # AI summarization
│       │   └── watcher.py      # File watcher daemon
│       └── data/
│           └── schema.sql      # Database schema
├── skill/
│   ├── SKILL.md               # Claude Code Skill
│   ├── REFERENCE.md           # Technical reference
│   └── INSTALL.md             # Installation guide
├── pyproject.toml
└── README.md
```

## Troubleshooting

**"Database not found" error:**
```bash
claude-finder init
```

**"No conversations found":**
- Verify `~/.claude/projects/` exists and contains JSONL files
- Use Claude Code to create some conversations first

**Slow summarization:**
```bash
# Skip AI summaries (faster, uses smart truncation)
claude-finder init --no-summarize
```

**Skill not activating:**
- Check Skill location: `ls ~/.claude/skills/conversation-search/SKILL.md`
- Verify YAML frontmatter format
- Restart Claude Code
- Try explicit trigger: "Search my conversations for X"

**Import errors:**
```bash
uv tool uninstall claude-finder
uv tool install claude-finder
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

Built for the Claude Code ecosystem. Uses Claude Haiku for intelligent message summarization.
