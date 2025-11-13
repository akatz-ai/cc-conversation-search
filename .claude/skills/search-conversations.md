# Search Conversations Skill

**When to use this skill:**
- User asks to search previous conversations
- User asks "what did we discuss about X?"
- User asks to find a specific topic from past chats
- User wants to recall something from earlier sessions
- User types `/search <query>`

## Instructions

You have access to **claude-finder**, a powerful conversation search system that indexes all Claude Code conversations with AI-generated summaries.

### NEW: Context-First Search (Default)

**The system now uses a context-first approach** where you READ recent conversation summaries directly instead of doing keyword searches. This lets you use semantic understanding to find relevant messages.

### CRITICAL: How to Run Search Commands

**ALWAYS use this exact pattern:**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 1
```

**Why?**
- Must `cd` to the claude-finder directory first
- Must activate the virtualenv
- Must chain with `&&` so if one fails, the rest don't run
- The search.py script needs the venv's Python packages

### Common Search Patterns

**1. Load Recent Context (NEW - Use this first!)**
```bash
# Load last 1 day (default for quick searches)
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 1

# Load last 3 days (for broader searches)
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 3

# Load last week
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 7
```

**2. Get Full Message Content (after identifying relevant UUIDs)**
```bash
# Fetch full content for one or more messages
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --full abc123de fgh456ij
```

**3. Legacy Keyword Search (fallback if context mode doesn't work)**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "authentication bug" --days 30
```

**4. List Conversations Only**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --list --days 7
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

### How to Use Context-First Search

**The new workflow:**

1. **Load context** - Get all recent conversation summaries into your context
2. **Read and understand** - Use your semantic understanding to identify relevant messages
3. **Fetch full content** - Get complete message text for the UUIDs you identified
4. **Answer the user** - Synthesize and present the relevant information

### Example Workflow

**User**: "What did we discuss about git yesterday?"

**Step 1: Load context**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 1
```

**Step 2: Read the output**
You'll see something like:
```
## [6319c5f7] Redream Frontend: Vue vs React Architecture
**485 msgs** | /home/akatzfey/projects/redream | Nov-13 08:51

👤 08:23 `7adb9397` User asks about git commit history
🤖 08:24 `27eb3931` Explained how to use git log with filters
👤 08:25 `742644d3` Thanks, that worked!
...
```

**Step 3: Identify relevant messages**
You spot messages `7adb9397` and `27eb3931` are about git.

**Step 4: Fetch full content**
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --full 7adb9397 27eb3931
```

**Step 5: Answer the user**
"Yesterday we discussed git commit history. You asked how to filter git logs, and I explained using `git log --since` and `--grep` options. Here's the full exchange: [show content]"

### When to Use Each Mode

- **--load**: Default for all searches. Loads summaries for semantic understanding.
- **--full UUID**: After identifying relevant messages, get their complete text.
- **--list**: Quick overview of recent conversations (just titles).
- **Legacy query**: Only if context mode fails or you need precise keyword matching.

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
