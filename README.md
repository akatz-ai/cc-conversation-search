# Conversation Search

Find and resume past Claude Code conversations using smart hybrid extraction and JIT indexing. Get session IDs and project paths to easily jump back into previous work.

## Features

- **Session Resumption**: Get exact commands to resume past conversations
- **Unified CLI**: Single `conversation-search` command with intuitive subcommands
- **Smart Extraction**: Hybrid indexing (full user content + smart assistant extraction)
- **JIT Indexing**: Instant indexing before search (no AI calls, no delays)
- **Progressive Exploration**: Simple search → broader search → manual exploration
- **Conversation Context**: Expand context incrementally around any message
- **Claude Code Skill**: Integrated Skill that outputs session resumption commands
- **Multi-Project Support**: Works across all your Claude Code projects

## Quick Start

### Installation via Claude Code Plugin (Recommended)

Install the complete plugin (skill + CLI tool instructions) directly in Claude Code:

```bash
# Add plugin to marketplace
/plugin marketplace add akatz-ai/cc-conversation-search

# Install the plugin
/plugin install conversation-search
```

Then follow the installation instructions shown by Claude to:
1. Install the CLI tool: `uv tool install cc-conversation-search`
2. Initialize the database: `conversation-search init`

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
conversation-search init
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
conversation-search search "authentication bug"

# Search with time filter
conversation-search search "react hooks" --days 30

# Get resume commands for a specific message
conversation-search resume <MESSAGE_UUID>
```

### Using with Claude Code Skill

Once installed, ask Claude:
- "Find that conversation where we discussed authentication"
- "Locate the conversation about React hooks"
- "What did we talk about regarding the database?"

**Auto-Installation**: If the CLI tool isn't installed, the skill will automatically attempt to install it via `uv` or `pip`, then initialize the database. In most cases, everything "just works" after installing the plugin!

Claude will show you the session ID, project path, and exact commands to resume the conversation.

## Command Reference

### `conversation-search init`
Initialize database and perform initial indexing
```bash
conversation-search init [--days 7] [--no-extract] [--force]
```

### `conversation-search index`
JIT index conversations (instant, no AI calls)
```bash
conversation-search index [--days N] [--all] [--no-extract]
```

**IMPORTANT**: The skill always runs `index` before `search` for fresh data.

### `conversation-search search`
Search conversations
```bash
conversation-search search "query" [--days N] [--project PATH] [--content] [--json]
```

### `conversation-search context`
Get context around a specific message
```bash
conversation-search context MESSAGE_UUID [--depth 5] [--content] [--json]
```

### `conversation-search list`
List recent conversations
```bash
conversation-search list [--days 7] [--limit 20] [--json]
```

### `conversation-search tree`
View conversation tree structure
```bash
conversation-search tree SESSION_ID [--json]
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
3. **Search**: FTS5 full-text search over extracted content with conversation tree traversal
4. **JIT Indexing**: Skill runs `index` before `search` for fresh data (instant, no AI calls)

## Claude Code Skill

The included Skill allows Claude to search your conversation history automatically.

**Example usage:**
```
User: "Find that conversation where we started implementing the API"
Claude: [Activates conversation-search Skill]
        [Runs Level 0: conversation-search index --days 7]  (instant JIT index)
        [Runs Level 1: conversation-search search "implementing API" --days 14 --json]
        [Finds match]
        [Displays session ID, project path, and resume commands]

        Output:
        Session: abc-123-session-id
        Project: /home/user/projects/myproject
        Time: 2025-11-13 22:50

        To resume:
          cd /home/user/projects/myproject
          claude --resume abc-123-session-id
```

See `skills/conversation-search/SKILL.md` for progressive search workflow and complete documentation.

## Advanced Usage

### JSON Output for Scripting

All commands support `--json` flag:
```bash
# Export search results
conversation-search search "authentication" --json > auth_convs.json

# Programmatic processing
conversation-search list --days 30 --json | jq '.[] | .conversation_summary'
```

### Programmatic Use

```python
from conversation_search.core.search import ConversationSearch
from conversation_search.core.indexer import ConversationIndexer

# Search for messages
search = ConversationSearch()
results = search.search_conversations("authentication", days_back=7)
for r in results:
    print(f"{r['message_uuid']}: {r['summary']}")  # UUID for branching

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
│       │   ├── indexer.py      # Conversation indexing
│       │   ├── search.py       # Search functionality
│       │   └── summarization.py # Smart hybrid extraction
│       └── data/
│           └── schema.sql      # Database schema
├── skills/
│   └── conversation-search/
│       ├── SKILL.md           # Claude Code Skill with progressive workflow
│       └── REFERENCE.md       # Complete command reference
├── pyproject.toml
└── README.md
```

## Troubleshooting

**"Database not found" error:**
```bash
conversation-search init
```

**"No conversations found":**
- Verify `~/.claude/projects/` exists and contains JSONL files
- Use Claude Code to create some conversations first

**Want to skip extraction and use raw content only:**
```bash
# Store only raw content (even faster, but less optimized for search)
conversation-search init --no-extract
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
