---
name: conversation-search
description: Search and retrieve context from previous Claude Code conversations. Use when the user asks about past conversations, wants to find previous discussions, references earlier work, or says things like "what did we discuss about X" or "find that conversation where". Requires claude-finder package.
allowed-tools: Bash
---

# Conversation Search

Search through your entire Claude Code conversation history with semantic search.

## Prerequisites

The `claude-finder` tool must be installed. Check if it's available:

```bash
claude-finder --help
```

If not installed:
```bash
uv tool install claude-finder
# OR
pip install claude-finder
```

Then initialize:
```bash
claude-finder init
```

## Core Commands

### Search
```bash
# Basic search
claude-finder search "authentication bug" --json

# Limit by time
claude-finder search "react hooks" --days 30 --json

# Show full content
claude-finder search "database migration" --content --json

# Filter by project
claude-finder search "api" --project /home/user/projects/myapp --json
```

### Get Context
```bash
# Get conversation context around a specific message
claude-finder context <MESSAGE_UUID> --depth 5 --json
```

### List Conversations
```bash
# List recent conversations
claude-finder list --days 7 --json
```

## When to Use This Skill

Activate this Skill when the user:
- Asks "what did we discuss about X?"
- Says "find that conversation where we..."
- Wants to reference previous work or decisions
- Asks about past bugs, features, or implementations
- Says "didn't we already talk about this?"
- Wants to see conversation history

## Usage Instructions

1. **Parse the user's question** to extract the search query
2. **Run the search** using `claude-finder search "<query>" --json`
3. **Parse the JSON output** which includes:
   - `message_uuid`: Unique message identifier
   - `timestamp`: When the message was sent
   - `message_type`: "user" or "assistant"
   - `summary`: AI-generated 1-2 sentence summary
   - `project_path`: Project location
   - `conversation_summary`: Conversation title
4. **Present results** to the user with relevant details
5. **Offer to expand** with `--content` flag or get more context with `claude-finder context`

## Output Format

All commands support `--json` flag for structured output. Always use `--json` when calling from this Skill.

**Search result format:**
```json
[
  {
    "message_uuid": "abc-123",
    "timestamp": "2025-01-13T10:30:00",
    "message_type": "user",
    "summary": "User asks about fixing authentication bug in login flow",
    "project_path": "/home/user/projects/myapp",
    "conversation_summary": "Authentication Bug Fix"
  }
]
```

## Tips for Effective Use

- **Always use `--json` flag** for structured output
- **Use `--days` to scope searches** (faster, more relevant)
- **Start with summaries** then expand with `--content` if needed
- **Use `context` command** to get full conversation flow
- **Filter by `--project`** when user mentions specific project

## Examples

**Example 1: User asks about past discussion**
```
User: "What did we discuss about React hooks last week?"
```

You should:
1. Run: `claude-finder search "react hooks" --days 7 --json`
2. Parse the JSON results
3. Present: "I found 3 conversations about React hooks from last week: [summarize results]"
4. Offer: "Would you like to see the full content of any of these?"

**Example 2: User wants to find specific conversation**
```
User: "Find that conversation where we fixed the database migration issue"
```

You should:
1. Run: `claude-finder search "database migration" --json`
2. Present the matching conversations
3. If multiple matches, help user narrow down
4. Offer to show context: `claude-finder context <uuid> --json`

**Example 3: User references recent work**
```
User: "Can you remind me what we decided about the API structure?"
```

You should:
1. Run: `claude-finder search "api structure" --days 14 --json`
2. Present the relevant decisions
3. Offer to show more context if needed

## Background Indexing (Optional)

Users can optionally run the watcher for real-time indexing:
```bash
# In a separate terminal or tmux
claude-finder watch
```

This monitors `~/.claude/projects` and automatically indexes new conversations. Not required for this Skill to work, but improves freshness of search results.

## Troubleshooting

**"Database not found" error:**
- User needs to run: `claude-finder init`

**"No results found":**
- Try broader search terms
- Increase `--days` range or omit for all-time search
- User may need to reindex: `claude-finder index --days 30`

**Tool not available:**
- Check if installed: `claude-finder --help`
- Install with: `uv tool install claude-finder` or `pip install claude-finder`
