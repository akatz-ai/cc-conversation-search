Search previous Claude Code conversations using claude-finder's context-first semantic search.

**Usage:**
```
/search [query or description]
```

**Examples:**
- `/search What did we discuss about authentication yesterday?`
- `/search Find the React hooks conversation from last week`
- `/search Show me database-related work from the past 3 days`

**How it works:**
1. Claude loads recent conversation summaries directly into context
2. Uses semantic understanding to identify relevant messages (no keyword guessing!)
3. Can fetch full message content for specific items you're interested in

**What Claude will do:**
- Load summaries from the requested timeframe (default: last 1-3 days)
- Read and understand them semantically
- Identify messages matching your question
- Show you the relevant conversations
- Optionally fetch full content if needed

**Advantages over old keyword search:**
- Semantic matching: "git stuff" matches "version control changes"
- See all context at once, not filtered results
- Natural language queries work better
- No need to guess exact keywords

**Note:** Requires claude-finder to be set up and the watcher daemon to be running for best results.
