# Search Conversations Skill

**When to use this skill:**
- User asks to search previous conversations
- User asks "what did we discuss about X?"
- User asks to find a specific topic from past chats
- User wants to recall something from earlier sessions

## Instructions

You have access to **claude-finder**, a powerful conversation search system that indexes all Claude Code conversations with AI-generated summaries.

### How to Search

When the user asks to search conversations, follow these steps:

1. **Run the search** using the Bash tool:
   ```bash
   cd /home/akatzfey/projects/redream/claude-finder
   source venv/bin/activate
   python3 src/search.py "search query" --days 30 --limit 10
   ```

2. **Format results** for the user:
   - Show the conversation summary
   - Show message summaries
   - Include timestamps
   - Show UUIDs for context expansion

3. **Offer progressive disclosure**:
   - "Would you like me to show the full context for any of these?"
   - "I can expand the conversation tree to show parent/child messages"
   - "I can show the full message content (not just the summary)"

### Available Search Options

**Basic search:**
```bash
python3 src/search.py "your search query"
```

**Search with filters:**
```bash
# Last 7 days only
python3 src/search.py "authentication" --days 7

# Specific project
python3 src/search.py "react hooks" --project /home/akatzfey/projects/myapp

# Show full content (not just summaries)
python3 src/search.py "database" --content

# More results
python3 src/search.py "api" --limit 20

# JSON output (for programmatic parsing)
python3 src/search.py "refactor" --json
```

**List recent conversations:**
```bash
python3 src/search.py --list --days 7
```

**Get conversation context (progressive disclosure):**
```bash
# Show context around a specific message
python3 src/search.py --context MESSAGE_UUID --depth 5

# Show full content in context
python3 src/search.py --context MESSAGE_UUID --depth 5 --content
```

**View conversation tree:**
```bash
python3 src/search.py --tree SESSION_ID
```

### Example Workflow

**User asks:** "What did we discuss about React hooks last week?"

**You do:**
1. Search:
   ```bash
   cd /home/akatzfey/projects/redream/claude-finder
   source venv/bin/activate
   python3 src/search.py "react hooks" --days 7 --content
   ```

2. Show results:
   ```
   I found 3 conversations about React hooks from last week:

   1. **[Nov 6, 14:23] React Hooks Debugging Session**
      Project: /home/user/projects/myapp

      User: "Why are my React hooks causing infinite re-renders?"
      Assistant: "The issue is calling setState in useEffect without dependencies..."

      UUID: abc-123-def

   2. **[Nov 8, 10:15] Custom Hooks Implementation**
      ...
   ```

3. Offer options:
   ```
   Would you like me to:
   - Show the full context for any of these conversations?
   - Resume the conversation at a specific point?
   - Search for something more specific?
   ```

### Tips

- **Use quotes** for multi-word searches: `"authentication bug"`
- **Search summaries first** (fast), then expand to full content if needed
- **Filter by date** to narrow results: `--days 7`
- **Check recent conversations** with `--list` if unsure what to search for
- **Progressive disclosure**: Start with summaries, expand context as needed

### Database Location

- Database: `~/.claude-finder/index.db`
- Search tool: `/home/akatzfey/projects/redream/claude-finder/src/search.py`
- Requires: Virtual environment activation

### Error Handling

If the database doesn't exist:
```
Error: Database not found. Run indexer first:
  python3 src/indexer.py --days 7
```

If no results found:
- Try broader search terms
- Increase `--days` parameter
- Check `--list` to see what conversations are indexed

### After Finding Results

Offer to:
1. **Show full context** - Expand the conversation tree around a message
2. **Resume conversation** - Note the session ID and offer to continue that discussion
3. **Refine search** - Try different search terms
4. **Show related messages** - Find other messages in the same conversation
