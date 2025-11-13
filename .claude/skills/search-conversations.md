# Search Conversations Skill

**When to use this skill:**
- User asks to search previous conversations
- User asks "what did we discuss about X?"
- User asks to find a specific topic from past chats
- User wants to recall something from earlier sessions
- User types `/search <query>`

## Instructions

You have access to **claude-finder**, a powerful conversation search system that indexes all Claude Code conversations with AI-generated summaries.

### CRITICAL: How to Run Search Commands

**ALWAYS use this exact pattern:**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "your query" --days 30
```

**Why?**
- Must `cd` to the claude-finder directory first
- Must activate the virtualenv
- Must chain with `&&` so if one fails, the rest don't run
- The search.py script needs the venv's Python packages

### Common Search Patterns

**1. Basic Search (most common)**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "authentication bug" --days 30
```

**2. List Recent Conversations**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --list --days 7
```

**3. Get Context Around a Message**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --context MESSAGE_UUID --depth 5
```

**4. Show Full Content (not just summaries)**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "database migration" --days 7 --content
```

### Error Handling

**If database is corrupted:**
```
Error: database disk image is malformed
```

**Fix:**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/indexer.py --days 7 --no-summarize
```

This rebuilds the database from scratch.

**If database doesn't exist:**
```
Error: Database not found
```

**Fix:** Run the indexer first (same command as above)

### How to Present Results

When you get search results, format them nicely:

1. **Show count**: "I found 5 conversations about authentication bugs"

2. **Show each result**:
   ```
   1. [Nov 10, 14:23] WebSocket Debugging Session
      Project: /home/user/projects/myapp

      User: "User asks about fixing websocket disconnection issues"
      Assistant: "Suggested checking connection timeout and reconnection logic"

      UUID: abc-123-def
   ```

3. **Offer options**:
   ```
   Would you like me to:
   - Show the full context for any of these?
   - Display the complete message content?
   - Search for something more specific?
   ```

### Search Tips

- **Single word**: Automatically uses prefix matching (e.g., "auth" matches "authentication")
- **Multiple words**: Searches for all terms (implicit AND)
- **Quotes**: Use for exact phrases: `"authentication error"`
- **Days filter**: `--days 7` for last week, `--days 30` for last month
- **Project filter**: `--project /home/user/projects/myapp`

### Progressive Disclosure Workflow

1. **Start with summaries** (default, fast)
2. **If user wants more**, expand context: `--context UUID --depth 5`
3. **If still not enough**, show full content: `--content`
4. **If they want to resume**, note the session ID and explain they can use `/resume`

### Example Conversation

**User**: What did we discuss about React hooks last week?

**You**:
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "react hooks" --days 7
```

**Then show results formatted nicely with the count, summaries, and options**

### Important Notes

- Database location: `~/.claude-finder/index.db`
- Search tool: `~/projects/redream/claude-finder/src/search.py`
- **Always** chain commands with `&&`
- **Always** activate venv
- **Always** cd to the directory first

### If Search Returns 0 Results

Try:
1. List recent conversations to see what's indexed: `--list`
2. Use broader search terms
3. Increase `--days` parameter
4. Check if the daemon is running to index new messages
