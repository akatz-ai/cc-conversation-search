# Claude Finder

A powerful conversation indexing and search system for Claude Code that enables semantic search across your entire conversation history with progressive disclosure.

## Features

- **Automatic Indexing**: Indexes conversations from `~/.claude/projects` with AI-generated summaries
- **Conversation Tree Tracking**: Maintains full tree structure including branches and checkpoints
- **Semantic Search**: Full-text search across Haiku-generated message summaries
- **Progressive Disclosure**: Expand conversation context incrementally as needed
- **Multi-Project Support**: Works across all your Claude Code projects
- **Efficient**: SQLite database with FTS5 for fast searches

## Architecture

```
~/.claude/
├── projects/           # Claude Code conversation files (JSONL)
│   └── {project}/
│       └── {session}.jsonl
└── ...

~/.claude-finder/
├── index.db           # SQLite database with indexed conversations
└── message_counter    # Hook counter for periodic indexing
```

### Database Schema

- **messages**: Individual messages with summaries, tree structure (parent_uuid), timestamps
- **conversations**: Session metadata with conversation summaries
- **message_summaries_fts**: FTS5 full-text search index
- **index_queue**: Processing queue for batch operations

## Installation

1. **Clone and setup**:
   ```bash
   cd /path/to/claude-finder
   chmod +x src/indexer.py src/search.py hooks/post-message.sh
   ```

2. **Initial indexing** (index last 7 days):
   ```bash
   python3 src/indexer.py --days 7
   ```

3. **Install hook** (optional - for automatic indexing):
   ```bash
   # Set the installation directory
   export CLAUDE_FINDER_DIR=/path/to/claude-finder

   # Create hooks directory if it doesn't exist
   mkdir -p ~/.claude/hooks

   # Install the hook
   ln -sf $CLAUDE_FINDER_DIR/hooks/post-message.sh ~/.claude/hooks/user-prompt-submit.sh
   ```

   The hook will automatically index new conversations every 10 messages.

## Usage

### Indexing

**Index recent conversations**:
```bash
# Index last 1 day (default)
python3 src/indexer.py

# Index last 7 days
python3 src/indexer.py --days 7

# Index all conversations
python3 src/indexer.py --all

# Fast indexing without summarization (for testing)
python3 src/indexer.py --no-summarize
```

### Searching

**Search conversations**:
```bash
# Search for a topic
python3 src/search.py "authentication bug"

# Search last 30 days
python3 src/search.py "react hooks" --days 30

# Search in specific project
python3 src/search.py "api endpoint" --project home/user/projects/myapp

# Show full content (not just summaries)
python3 src/search.py "database migration" --content

# Output as JSON
python3 src/search.py "refactor" --json
```

**List recent conversations**:
```bash
# List recent conversations
python3 src/search.py --list

# List last 30 days
python3 src/search.py --list --days 30
```

**Get conversation context**:
```bash
# Get context around a specific message
python3 src/search.py --context MESSAGE_UUID

# Get more parent context (default: 3 levels)
python3 src/search.py --context MESSAGE_UUID --depth 5

# Show full content
python3 src/search.py --context MESSAGE_UUID --content
```

**View conversation tree**:
```bash
# Show full conversation tree structure
python3 src/search.py --tree SESSION_ID

# As JSON
python3 src/search.py --tree SESSION_ID --json
```

## How It Works

1. **Indexer** (`src/indexer.py`):
   - Scans `~/.claude/projects/` for JSONL conversation files
   - Parses each conversation into a tree structure using `parentUuid` references
   - Calls Haiku via `claude` CLI to generate 1-2 sentence summaries for each message
   - Stores in SQLite with full-text search indices

2. **Search** (`src/search.py`):
   - Provides semantic search over summaries using SQLite FTS5
   - Implements progressive disclosure: start with summaries, expand to full content as needed
   - Traverses conversation trees to provide context (ancestors/children)
   - Supports filtering by date, project, and more

3. **Hook** (`hooks/post-message.sh`):
   - Triggers every 10th message (to minimize overhead)
   - Runs indexer in background to update index
   - Uses lock file to prevent concurrent indexing

## Claude Integration

Claude can use this tool to help you find past conversations. Simply ask:

- "Search our previous conversations about authentication"
- "What did we discuss about React hooks last week?"
- "Find that conversation where we fixed the database migration issue"

Claude will:
1. Search the indexed summaries
2. Show you relevant matches
3. Progressively expand context as needed
4. Offer to resume the conversation at that exact point

## Example Workflow

```bash
# 1. Initial setup - index last week
python3 src/indexer.py --days 7

# 2. Search for something
python3 src/search.py "websocket connection"

# Output:
# 🔍 Found 3 matches for 'websocket connection':
#
# 👤  [2025-11-10 14:23] home/user/projects/myapp
#    Summary: User asks about fixing websocket disconnection issues in production
#    UUID: abc-123-def
#    Conversation: WebSocket Debugging Session
#
# 🤖  [2025-11-10 14:25] home/user/projects/myapp
#    Summary: Suggested checking connection timeout settings and implementing reconnection logic
#    UUID: def-456-ghi
#    Conversation: WebSocket Debugging Session

# 3. Get more context on the first match
python3 src/search.py --context abc-123-def --depth 5 --content

# 4. Resume conversation (use Claude Code's resume feature)
# Copy the session ID and use: claude --resume
```

## Performance Considerations

- **Summarization**: Uses Haiku for fast, cheap summaries (~1-2 sentences per message)
- **Indexing Speed**: ~10-50 messages/second (depends on Haiku API latency)
- **Storage**: ~1-2KB per message (summary + metadata)
- **Search Speed**: SQLite FTS5 is very fast, even with 100K+ messages

## Future Enhancements

- [ ] Vector embeddings for semantic similarity search
- [ ] Web UI for conversation tree visualization
- [ ] Direct integration with `claude --resume` command
- [ ] Incremental indexing (only new messages)
- [ ] Export conversation branches as markdown
- [ ] Conversation analytics (topics, frequency, etc.)

## Troubleshooting

**"Database not found" error**:
```bash
# Run indexer first to create database
python3 src/indexer.py
```

**Summarization is slow**:
```bash
# Use --no-summarize for testing
python3 src/indexer.py --no-summarize

# Or increase batch size / use faster model in future
```

**Hook not working**:
```bash
# Check if hook is installed
ls -la ~/.claude/hooks/user-prompt-submit.sh

# Check hook execution
tail -f ~/.claude/debug/*
```

## License

MIT (or whatever you prefer)

## Contributing

PRs welcome! This is an experimental tool to improve Claude Code workflow.
