# Claude Finder Background Daemon

The watcher daemon is the **recommended way** to keep your conversation index up-to-date with **zero lag** during conversations.

## Why Use the Daemon?

**Problems with the hook approach:**
- Adds lag after every 10th message
- Runs synchronously during your conversation
- Can't distinguish between tool calls and end of turn

**Benefits of the daemon:**
- **Zero lag** - runs completely in the background
- Detects when conversation files update
- Waits for Claude to finish responding (not just tool calls)
- Batches messages efficiently (every 30 seconds or 20 messages)
- Completely asynchronous

## How It Works

1. **Watches** `~/.claude/projects` for file changes using `watchdog`
2. **Detects** when conversation JSONL files are modified
3. **Identifies** messages that need AI summarization (vs truncated content)
4. **Batches** them for efficiency
5. **Calls** `claude --model haiku` to generate summaries
6. **Updates** the SQLite database asynchronously

## Running the Daemon

### Basic Usage

```bash
cd /path/to/claude-finder
source venv/bin/activate
python3 src/watcher_daemon.py
```

Output:
```
Claude Finder Watcher Daemon
==================================================
Running initial indexing (without summaries)...
Found 15 conversation files to index
...
✓ Initial indexing complete

Watching: /home/user/.claude/projects
Batch size: 10 messages (or 30s delay)
Press Ctrl+C to stop

[14:23:15] Processing 1 updated conversations...
  6319c5f7-368f-4853-b1da-9dedc1d338f2.jsonl: 5 messages need summarization
  Calling Haiku to summarize batch of 5 messages...
    ✓ Updated 5 summaries
  ✓ Total: 5 message summaries updated
```

## Running in the Background

### Option 1: tmux (Simple)

```bash
# Start a new tmux session
tmux new -s claude-finder

# Inside tmux
cd /path/to/claude-finder
source venv/bin/activate
python3 src/watcher_daemon.py

# Detach from tmux: Ctrl+B then D

# Later, reattach to see status:
tmux attach -t claude-finder
```

### Option 2: systemd User Service (Advanced)

Create `~/.config/systemd/user/claude-finder.service`:

```ini
[Unit]
Description=Claude Finder Watcher Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_USERNAME/path/to/claude-finder
ExecStart=/home/YOUR_USERNAME/path/to/claude-finder/venv/bin/python3 src/watcher_daemon.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

**Update the paths** in the service file, then:

```bash
# Enable and start the service
systemctl --user daemon-reload
systemctl --user enable claude-finder
systemctl --user start claude-finder

# Check status
systemctl --user status claude-finder

# View logs
journalctl --user -u claude-finder -f
```

### Option 3: nohup (Quick & Dirty)

```bash
cd /path/to/claude-finder
source venv/bin/activate
nohup python3 src/watcher_daemon.py > ~/claude-finder.log 2>&1 &

# Check it's running
ps aux | grep watcher_daemon

# View logs
tail -f ~/claude-finder.log
```

## Configuration

The daemon has sensible defaults:

- **Batch size**: 20 messages at a time
- **Minimum interval**: 30 seconds between batches
- **Initial index**: Runs `indexer.py --days 1 --no-summarize` on startup

You can modify these in `src/watcher_daemon.py`:

```python
# In ConversationWatcher.__init__()
self.batch_size = 20              # Messages per batch
self.min_batch_interval = 30      # Seconds between batches

# In call_haiku_summarizer()
timeout=60                        # Timeout for Claude CLI calls

# In main()
batch_size = 20                   # Adjust batch processing
```

## Monitoring

### Check if it's running

```bash
# With tmux
tmux ls
tmux attach -t claude-finder

# With systemd
systemctl --user status claude-finder

# With ps
ps aux | grep watcher_daemon.py
```

### View activity

The daemon prints status messages whenever it processes messages:

```
[14:23:15] Processing 1 updated conversations...
  conversation-uuid.jsonl: 5 messages need summarization
  Calling Haiku to summarize batch of 5 messages...
    ✓ Updated 5 summaries
  ✓ Total: 5 message summaries updated
```

## Troubleshooting

### Daemon not starting

```bash
# Check database exists
ls -la ~/.claude-finder/index.db

# If not, run indexer first
python3 src/indexer.py --days 7 --no-summarize
```

### No summaries being generated

1. Check if the daemon is running:
   ```bash
   ps aux | grep watcher_daemon
   ```

2. Check if messages are actually unsummarized:
   ```bash
   sqlite3 ~/.claude-finder/index.db "
   SELECT COUNT(*) FROM messages
   WHERE summary LIKE '%...'
   LIMIT 5
   "
   ```

3. Check Claude CLI is working:
   ```bash
   echo "test" | claude --model haiku
   ```

### High CPU usage

The daemon is very lightweight, but if you notice high CPU:

- Increase `min_batch_interval` (default: 30s)
- Reduce `batch_size` (default: 20 messages)
- Check if you have many large conversation files updating frequently

## Comparison: Daemon vs Hook vs Manual

| Method | Lag | Auto | Background | Haiku |
|--------|-----|------|------------|-------|
| **Daemon** | None | ✓ | ✓ | ✓ |
| Hook | ~1-2s every 10 msgs | ✓ | Partial | ✓ |
| Manual | None | ✗ | ✗ | Optional |

**Recommendation**: Use the daemon for the best experience!
