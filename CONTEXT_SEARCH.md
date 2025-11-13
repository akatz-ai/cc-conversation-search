# Context-First Search: Implementation Notes

## Overview

Implemented a **context-first semantic search** approach that loads conversation summaries directly into Claude's context instead of relying on keyword-based FTS5 searches.

## Key Concept

**Old way (Tool-First):**
```
User query → Keyword extraction → FTS5 search → Filtered results → Optional expansion
```

**New way (Context-First):**
```
Time filter → Load all summaries → Claude reads & understands → Identify relevant UUIDs → Fetch full content
```

## Implementation

### New Methods in `ConversationSearch` class

1. **`load_context(days_back, project_path, ...)`**
   - Loads recent conversations with message summaries
   - Returns token-efficient markdown format
   - Default: last 1 day, max 10 conversations, 50 messages per conversation
   - Output format:
     ```markdown
     ## [session_id] Conversation Title
     **N msgs** | project/path | Date Time

     👤 HH:MM `uuid` User message summary
     🤖 HH:MM `uuid` Assistant message summary
     🌿 HH:MM `uuid` Branched message
     ```

2. **`get_full_messages(uuids)`**
   - Batch fetch full content for identified messages
   - Supports UUID prefixes (8 chars minimum)
   - Returns list of complete message dicts

### CLI Changes

New flags:
- `--load` - Load context mode (replaces keyword search)
- `--full UUID [UUID...]` - Fetch full content for message(s)
- Existing `query` parameter now labeled as "legacy keyword search"

### Usage Examples

**Load last day:**
```bash
python3 src/search.py --load --days 1
```

**Load last week:**
```bash
python3 src/search.py --load --days 7
```

**Fetch full messages (supports prefixes):**
```bash
python3 src/search.py --full 7adb9397 27eb3931
```

## Token Efficiency

Approximate token costs:
- Conversation header: ~30 tokens
- Message line: ~40 tokens
- 1 day active coding: ~4k-8k tokens
- 1 week: ~20k-40k tokens
- 1 month: ~80k-160k tokens (approaching budget)

## Advantages

1. **Semantic understanding** - "git stuff" matches "version control"
2. **No keyword guessing** - Claude sees all options
3. **Context awareness** - Understands conversation flow
4. **Natural UX** - Like talking to someone with perfect memory
5. **Progressive disclosure** - Start with summaries, drill to full content

## Workflow

1. User asks: "What did we discuss about X yesterday?"
2. Claude runs: `--load --days 1`
3. Claude reads summaries, identifies relevant messages
4. Claude runs: `--full <uuid1> <uuid2>`
5. Claude synthesizes and answers

## Files Modified

- `src/search.py` - Added load_context(), get_full_messages(), CLI args
- `.claude/skills/search-conversations.md` - Updated workflow documentation
- `.claude/commands/search.md` - Updated command description

## Legacy Support

Old FTS5 keyword search still available:
```bash
python3 src/search.py "keyword query" --days 7
```

Use when:
- Context budget exceeded
- Very old conversations (months back)
- Precise keyword matching needed

## Future Enhancements

- Auto-detect time range from query ("yesterday", "last week")
- Conversation summary tier (load titles first, then details)
- Exclude current session from search results
- Token budget warnings
