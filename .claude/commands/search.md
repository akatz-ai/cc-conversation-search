Search previous Claude Code conversations using claude-finder.

**Usage:**
```
/search <query>
```

**Examples:**
- `/search authentication bug` - Find discussions about authentication bugs
- `/search react hooks` - Find conversations about React hooks
- `/search database migration` - Find database migration discussions

**What this does:**
Claude will search your indexed conversation history using AI-generated summaries and show you relevant matches with progressive disclosure options.

**Options:**
After showing results, Claude can:
- Show full context around a message
- Display the complete conversation tree
- Show full message content (not just summaries)
- Help you resume that conversation

**Note:** Requires claude-finder to be set up and the watcher daemon to be running for best results.
