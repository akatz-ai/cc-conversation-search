# Conversation Search Skill for Claude Code

Enable Claude to search through your entire conversation history automatically.

## Quick Install

### 1. Install the tool
```bash
uv tool install claude-finder
```

### 2. Initialize
```bash
claude-finder init
```

### 3. Install the Skill
```bash
mkdir -p ~/.claude/skills/conversation-search
cp SKILL.md REFERENCE.md ~/.claude/skills/conversation-search/
```

### 4. Use it!
Ask Claude:
```
What did we discuss about authentication last week?
```

Claude will automatically:
1. Activate the conversation-search Skill
2. Run `claude-finder search "authentication" --days 7 --json`
3. Present relevant conversations with summaries
4. Offer to show more context

## Files

- **SKILL.md** - Main Skill definition (required)
- **REFERENCE.md** - Complete technical reference (optional but recommended)
- **INSTALL.md** - Detailed installation guide

## How It Works

1. **Tool Installation**: `claude-finder` must be installed and available in PATH
2. **Skill Activation**: Claude detects relevant questions and activates the Skill
3. **Search Execution**: Skill runs `claude-finder` commands via Bash tool
4. **Result Presentation**: Claude parses JSON output and presents findings

## Commands Available to Claude

```bash
# Search
claude-finder search "<query>" --json [--days N] [--project PATH]

# Context
claude-finder context <UUID> --json [--depth N]

# List conversations
claude-finder list --json [--days N]

# View tree
claude-finder tree <SESSION_ID> --json
```

## Customization

### For Personal Use
Install to `~/.claude/skills/conversation-search/`

### For Team Use
Install to `.claude/skills/conversation-search/` in your project and commit to git.

Team members get the Skill automatically when they pull.

## Background Indexing (Optional)

Keep the index updated in real-time:
```bash
# In a separate terminal or tmux
claude-finder watch
```

## Troubleshooting

**Skill not activating?**
- Check location: `ls ~/.claude/skills/conversation-search/SKILL.md`
- Restart Claude Code
- Try explicit trigger: "Search my conversations for X"

**Tool not found?**
- Verify: `claude-finder --help`
- Check PATH includes uv bin dir: `echo $PATH`
- Reinstall: `uv tool install claude-finder --force`

**No results found?**
- Initialize: `claude-finder init`
- Reindex: `claude-finder index --days 30`

## Requirements

- Python 3.9+
- Claude Code CLI (`claude` command)
- Anthropic API key (for AI summarization, optional)

## Learn More

- **SKILL.md** - How Claude uses this Skill
- **REFERENCE.md** - Complete command reference and technical details
- **INSTALL.md** - Step-by-step installation for all scenarios

## License

MIT
