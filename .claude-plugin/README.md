# Conversation Search Plugin

This plugin provides semantic search across your Claude Code conversation history with progressive exploration strategies.

## Installation

### Option 1: Install from GitHub (Recommended)

Users can install directly from your GitHub repository:

```bash
# Add plugin to marketplace
/plugin marketplace add akatz-ai/cc-conversation-search

# Install the plugin
/plugin install conversation-search
```

This will:
- Install the conversation-search skill
- Display installation instructions for the CLI tool

### Option 2: Manual Installation

1. Clone the repository
2. Install the CLI tool:
   ```bash
   uv tool install cc-conversation-search
   # OR
   pip install cc-conversation-search
   ```
3. Initialize the database:
   ```bash
   conversation-search init
   ```
4. Copy the skill to Claude Code:
   ```bash
   mkdir -p ~/.claude/skills/conversation-search
   cp skills/conversation-search/* ~/.claude/skills/conversation-search/
   ```

## Updates

When you publish updates to GitHub, users can update by:

```bash
/plugin update conversation-search
```

This will pull the latest skill files automatically.

## What's Included

- **Skill**: conversation-search (with progressive search workflow)
- **CLI Tool**: conversation-search command-line interface
- **Database**: Local SQLite index of conversations

## Requirements

- Claude Code
- Python 3.9+
- Either `uv` or `pip` for installation
