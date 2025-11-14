# Installation Instructions

Thank you for installing the **conversation-search** plugin!

## Step 1: Install the CLI Tool

The skill requires the `conversation-search` CLI tool.

**Note**: The package name is `cc-conversation-search` but the command is `conversation-search`.

### Recommended: Using uv
```bash
uv tool install cc-conversation-search
```

### Alternative: Using pip
```bash
pip install cc-conversation-search
```

## Step 2: Initialize the Database

Create the search index for your conversation history:

```bash
conversation-search init
```

This will:
- Create `~/.conversation-search/index.db`
- Index your last 7 days of conversations
- Extract searchable content using smart hybrid extraction (instant, no AI calls)

## Step 3: Test the Installation

Verify everything is working:

```bash
conversation-search search "test" --json
```

## You're Ready!

The **conversation-search** skill is now active. Try asking Claude:

- "Find that message where we discussed authentication"
- "What did we talk about regarding React hooks?"
- "Locate the conversation where we fixed the database bug"

Claude will use a progressive search strategy to find specific message UUIDs you can branch from.

## Troubleshooting

**Tool not found:**
- Make sure `conversation-search` is in your PATH
- Try: `which conversation-search`

**No conversations found:**
- Verify `~/.claude/projects/` exists and contains .jsonl files
- Try: `conversation-search list --days 30`

**For help:**
- Documentation: https://github.com/akatz-ai/cc-conversation-search
- Issues: https://github.com/akatz-ai/cc-conversation-search/issues
