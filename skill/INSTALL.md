# Installation Guide - Conversation Search Skill

## Quick Start

### 1. Install the tool

**Option A: Using uv (recommended)**
```bash
uv tool install claude-finder
```

**Option B: Using pip**
```bash
pip install claude-finder
```

**Option C: From source (development)**
```bash
git clone https://github.com/yourusername/claude-finder
cd claude-finder
uv tool install -e .
```

### 2. Verify installation

```bash
claude-finder --help
```

You should see the command help with subcommands.

### 3. Initialize the database

```bash
claude-finder init
```

This will:
- Create `~/.claude-finder/index.db`
- Index conversations from the last 7 days
- Generate AI summaries

### 4. Install the Skill

**For personal use:**
```bash
mkdir -p ~/.claude/skills/conversation-search
cp skill/SKILL.md ~/.claude/skills/conversation-search/
cp skill/REFERENCE.md ~/.claude/skills/conversation-search/
```

**For team/project use:**
```bash
mkdir -p .claude/skills/conversation-search
cp skill/SKILL.md .claude/skills/conversation-search/
cp skill/REFERENCE.md .claude/skills/conversation-search/
git add .claude/skills/
git commit -m "Add conversation search Skill"
```

### 5. Test the Skill

Ask Claude:
```
What did we discuss about authentication recently?
```

Claude should automatically use the conversation-search Skill to search your history.

---

## Detailed Setup

### Prerequisites

- **Python 3.9+**
- **Claude Code CLI** (`claude` command available)
- **Anthropic API key** (for AI summarization, optional but recommended)

### Claude CLI Setup

The tool uses Claude Code's CLI in headless mode for generating summaries.

1. Install Claude Code if not already installed
2. Login/verify: `claude --version`
3. Ensure API key is configured (the `claude` CLI handles this)

**Note:** Without Claude CLI, you can still use the tool with `--no-summarize` flag (uses smart truncation instead).

### Installation Methods Compared

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| `uv tool install` | Recommended | Isolated, clean | Requires uv |
| `pip install` | Simple | Works everywhere | May conflict with system packages |
| `pip install -e .` | Development | Live edits | Local only |

### Configuration

**Database location:** `~/.claude-finder/index.db`

**No configuration file needed** - all settings are command-line flags.

**Optional environment variables:**
```bash
# Custom database path (advanced)
export CLAUDE_FINDER_DB=~/.custom/path/index.db
```

---

## First-Time Indexing

### Quick Index (7 days)
```bash
claude-finder init
```

### Full Index (all conversations)
```bash
claude-finder init --days 365  # Or higher
```

### Fast Index (no AI summaries)
```bash
claude-finder init --no-summarize
```

**Recommendation:** Start with 7-30 days to test, then extend as needed.

---

## Keeping Index Updated

### Option 1: Manual (simple)
Run periodically:
```bash
claude-finder index --days 7
```

### Option 2: Watcher (automatic)
Run in background:
```bash
# In tmux/screen
claude-finder watch

# Or as a background job
nohup claude-finder watch > ~/.claude-finder/watcher.log 2>&1 &
```

### Option 3: Cron (scheduled)
```bash
# Add to crontab
0 */6 * * * /usr/local/bin/claude-finder index --days 1
```

**Recommendation:** Use watcher during active development, cron for passive maintenance.

---

## Skill Installation

### Personal Skill (just for you)

```bash
cd /path/to/claude-finder
mkdir -p ~/.claude/skills/conversation-search
cp skill/SKILL.md ~/.claude/skills/conversation-search/
cp skill/REFERENCE.md ~/.claude/skills/conversation-search/
```

### Project Skill (for your team)

```bash
cd /path/to/your-project
mkdir -p .claude/skills/conversation-search
cp /path/to/claude-finder/skill/SKILL.md .claude/skills/conversation-search/
cp /path/to/claude-finder/skill/REFERENCE.md .claude/skills/conversation-search/
git add .claude/skills/
git commit -m "Add conversation search Skill"
git push
```

Team members will automatically get the Skill when they pull.

### Verify Skill Installation

Ask Claude:
```
What Skills do you have available?
```

You should see `conversation-search` in the list.

---

## Testing

### Test the tool directly

```bash
# Index some data
claude-finder init --days 7

# Search
claude-finder search "authentication" --json

# List conversations
claude-finder list --days 7
```

### Test the Skill

Start a conversation with Claude and ask:
```
Can you search our previous conversations for discussions about React hooks?
```

Claude should:
1. Activate the conversation-search Skill
2. Run `claude-finder search "react hooks" --json`
3. Parse the results
4. Present findings to you

---

## Troubleshooting

### "claude-finder: command not found"

**With uv:**
```bash
# Check if installed
uv tool list

# Ensure uv bin dir is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Reinstall
uv tool install claude-finder --force
```

**With pip:**
```bash
# Check installation
pip show claude-finder

# Ensure pip bin dir is in PATH
python -m site --user-base  # Find user base
export PATH="$(python -m site --user-base)/bin:$PATH"
```

### "Database not found"

Run initialization:
```bash
claude-finder init
```

### "No conversations found"

Check if Claude Code projects exist:
```bash
ls ~/.claude/projects/
```

If empty, use Claude Code first to create some conversations, then run `claude-finder init`.

### Skill not activating

1. Check Skill location:
   ```bash
   ls ~/.claude/skills/conversation-search/SKILL.md
   ```

2. Verify YAML frontmatter format (must start with `---`)

3. Restart Claude Code

4. Try explicitly mentioning the trigger:
   ```
   Search my previous conversations for "authentication"
   ```

### Import errors after installation

Ensure Python 3.9+:
```bash
python --version
```

Reinstall:
```bash
uv tool uninstall claude-finder
uv tool install claude-finder
```

### Slow performance

1. **Limit search scope:**
   ```bash
   claude-finder search "query" --days 30
   ```

2. **Skip summarization** (faster but less accurate):
   ```bash
   claude-finder init --no-summarize
   ```

3. **Index incrementally:**
   ```bash
   claude-finder index --days 1  # Just today
   ```

---

## Upgrading

### Upgrade the tool

```bash
# With uv
uv tool upgrade claude-finder

# With pip
pip install --upgrade claude-finder
```

### Update the Skill

```bash
cd /path/to/claude-finder
git pull  # If installed from source

# Copy updated Skill files
cp skill/SKILL.md ~/.claude/skills/conversation-search/
cp skill/REFERENCE.md ~/.claude/skills/conversation-search/
```

### Migrate database (if schema changed)

Usually not needed, but if there are breaking changes:
```bash
# Backup old database
cp ~/.claude-finder/index.db ~/.claude-finder/index.db.backup

# Reinitialize
claude-finder init --force --days 30
```

---

## Uninstalling

### Remove the tool

```bash
# With uv
uv tool uninstall claude-finder

# With pip
pip uninstall claude-finder
```

### Remove the Skill

```bash
# Personal
rm -rf ~/.claude/skills/conversation-search

# Project
rm -rf .claude/skills/conversation-search
git commit -am "Remove conversation search Skill"
```

### Remove data

```bash
rm -rf ~/.claude-finder
```

---

## Next Steps

After installation:

1. **Test basic search:** `claude-finder search "test"`
2. **Try the Skill:** Ask Claude to search your conversations
3. **Set up watcher** (optional): `claude-finder watch`
4. **Read reference:** See `REFERENCE.md` for advanced usage

**Get help:**
- Tool help: `claude-finder <command> --help`
- Skill documentation: Available in `~/.claude/skills/conversation-search/`
- Issues: https://github.com/yourusername/claude-finder/issues
