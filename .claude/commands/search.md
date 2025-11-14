Search previous Claude Code conversations using claude-finder's message-level semantic search.

**Usage:**
```
/search [query or description]
```

**Examples:**
- `/search What did we discuss about authentication yesterday?`
- `/search Find the React hooks conversation from last week`
- `/search Show me database-related work from the past 3 days`

## How It Works

Claude-finder maintains an indexed database of all your Claude Code conversations with AI-generated message summaries (~50 tokens each). This allows semantic search across days of conversation history while staying within context limits.

**Progressive disclosure strategy:**
1. Load message summaries for the time period (default: 1-3 days)
2. Read and semantically understand all messages
3. Identify relevant messages matching your query
4. Fetch full content for specific messages if needed

## Tool Usage

**CRITICAL: Always use this exact pattern for running commands:**

```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py [args]
```

**Why?**
- Must `cd` to the claude-finder directory first
- Must activate the virtualenv with `source venv/bin/activate`
- Must chain with `&&` so if one fails, the rest don't run
- The search.py script needs the venv's Python packages

### Load Message Summaries (Primary Search Method)

```bash
# Load last 1 day (default for quick searches)
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 1

# Load last 3 days (for broader searches)
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 3

# Load last week
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 7
```

This returns markdown-formatted message summaries grouped by conversation. Each message shows:
- Time, message type (user/assistant)
- Short UUID (first 8 chars)
- AI-generated summary (~50 tokens)

**Token efficiency:**
- 1 day: ~150-200 messages = ~10k tokens
- 3 days: ~500 messages = ~30k tokens
- 7 days: ~1000 messages = ~60k tokens

### Fetch Full Message Content

After identifying relevant messages from summaries, fetch full content:

```bash
# Fetch full content for one or more messages (use short or full UUIDs)
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --full abc123de fgh456ij
```

### List Conversations Only

```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --list --days 7
```

### Legacy Keyword Search (fallback)

```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py "authentication bug" --days 30
```

## Typical Workflow

**User asks:** "What did we discuss about authentication last week?"

**Your approach:**

1. **Load summaries** for the relevant time period:
   ```bash
   cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --load --days 7
   ```

2. **Read the output** - you'll see something like:
   ```
   ## [6319c5f7] Redream Frontend: Vue vs React Architecture
   **485 msgs** | /home/akatzfey/projects/redream | Nov-13 08:51

   👤 08:23 `7adb9397` User asks about JWT vs sessions for authentication
   🤖 08:24 `27eb3931` Explained tradeoffs between JWT and session-based auth
   👤 08:25 `742644d3` Requests help implementing OAuth2 with Google
   ...
   ```

3. **Identify relevant messages** using your semantic understanding of the summaries

4. **Fetch full details** if needed:
   ```bash
   cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --full 7adb9397 27eb3931
   ```

5. **Answer the user** with context from the messages you found

## Advantages Over Keyword Search

- **Semantic matching:** "git stuff" matches "version control changes"
- **See all context:** Not filtered by keywords, you read everything and decide
- **Natural language queries:** Works better than guessing exact keywords
- **Time-based scoping:** Focus on recent conversations without manual filtering

## Error Handling

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

**Fix:** Run the indexer first:
```bash
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/indexer.py --days 7
```

## Important Notes

- Database location: `~/.claude-finder/index.db`
- **Always** chain commands with `&&`
- **Always** activate venv
- **Always** cd to the directory first
- Tool noise (Read/Glob/etc.) is automatically filtered out
- Summaries are immutable once generated (no staleness issues)
- Requires watcher daemon running for real-time indexing, or manual indexer runs

## Retroactive Summarization

If messages are indexed but not summarized:

```bash
# Summarize last 100 unsummarized messages
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --summarize 100

# Summarize all unsummarized from last 7 days
cd ~/projects/redream/claude-finder && source venv/bin/activate && python3 src/search.py --summarize --days 7
```
