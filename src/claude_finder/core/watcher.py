#!/usr/bin/env python3
"""
Claude Finder Watcher Daemon
Monitors ~/.claude/projects for conversation updates and triggers summarization
"""

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from claude_finder.core.summarization import MessageSummarizer, is_summarizer_conversation


class ConversationWatcher(FileSystemEventHandler):
    """Watches conversation files and tracks unsummarized messages"""

    def __init__(self, db_path: Path, batch_size: int = 10, verbose: bool = False):
        self.db_path = db_path
        self.batch_size = batch_size
        self.pending_files: Set[Path] = set()
        self.last_process_time = time.time()
        self.last_change_time = time.time()  # Track when last file change occurred
        self.idle_threshold = 30  # Process if no changes for 30 seconds
        self.verbose = verbose
        self.summarizer = MessageSummarizer(db_path=str(db_path))

    def on_modified(self, event):
        """Called when a file is modified"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only watch .jsonl conversation files (not agent files)
        if file_path.suffix == '.jsonl' and not file_path.stem.startswith('agent-'):
            if self.verbose:
                print(f"  📝 Detected change: {file_path.name}")

            self.pending_files.add(file_path)
            self.last_change_time = time.time()  # Update last change timestamp

    def get_unsummarized_messages(self, conv_file: Path) -> List[Dict]:
        """
        Get messages from a conversation file that don't have summaries yet

        A message needs summarization if:
        1. It exists in the DB (has been indexed)
        2. Its summary is truncated or it's not marked as summarized
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Read all messages from the conversation file
        file_messages = []
        session_id = None

        with open(conv_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())

                    if line_num == 1 and data.get('type') == 'summary':
                        continue

                    if 'uuid' in data and 'message' in data:
                        msg_type = data.get('type')
                        if msg_type not in ('user', 'assistant'):
                            continue

                        if not session_id:
                            session_id = data.get('sessionId')

                        # Extract content
                        msg_content = data['message'].get('content', '')
                        if isinstance(msg_content, list):
                            text_parts = []
                            for block in msg_content:
                                if isinstance(block, dict):
                                    if block.get('type') == 'text':
                                        text_parts.append(block.get('text', ''))
                                    elif block.get('type') == 'tool_use':
                                        tool_name = block.get('name', 'unknown')
                                        text_parts.append(f"[Tool: {tool_name}]")
                            msg_content = '\n'.join(text_parts)

                        file_messages.append({
                            'uuid': data['uuid'],
                            'message_type': msg_type,
                            'content': msg_content,
                            'timestamp': data.get('timestamp')
                        })

                except json.JSONDecodeError:
                    continue

        if not session_id or not file_messages:
            conn.close()
            return []

        # Check which messages are in DB and need summarization
        unsummarized = []

        for msg in file_messages:
            cursor.execute("""
                SELECT message_uuid, summary, full_content, is_summarized
                FROM messages
                WHERE message_uuid = ?
            """, (msg['uuid'],))

            result = cursor.fetchone()

            if result and not result['is_summarized']:
                # Message exists but not summarized yet
                should_summarize, reason = self.summarizer.needs_summarization(msg)
                if should_summarize:
                    unsummarized.append(msg)

        conn.close()
        return unsummarized

    def process_pending(self):
        """Process pending files and summarize messages"""
        if not self.pending_files:
            return

        time_since_change = time.time() - self.last_change_time
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing {len(self.pending_files)} updated conversations (idle for {int(time_since_change)}s)...")

        # Step 1: Re-index modified conversations to catch new messages
        from claude_finder.core.indexer import ConversationIndexer
        indexer = ConversationIndexer(db_path=str(self.db_path))

        for conv_file in list(self.pending_files):
            if not conv_file.exists():
                self.pending_files.remove(conv_file)
                continue

            try:
                # Skip summarizer conversations
                with open(conv_file, 'r') as f:
                    messages = []
                    for line in f:
                        try:
                            data = json.loads(line.strip())
                            if 'uuid' in data:
                                messages.append({'content': str(data), 'message_type': 'user'})
                        except:
                            pass

                if is_summarizer_conversation(conv_file, messages):
                    self.pending_files.remove(conv_file)
                    continue

                # Index conversation (adds new messages to DB without AI summaries)
                # Suppress stdout to avoid noise
                import sys, io
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    indexer.index_conversation(conv_file, summarize=False)
                finally:
                    sys.stdout = old_stdout

            except Exception as e:
                print(f"  Error indexing {conv_file.name}: {e}")

        indexer.close()

        # Step 2: Collect unsummarized messages from indexed conversations
        all_unsummarized = []

        for conv_file in list(self.pending_files):
            if not conv_file.exists():
                continue

            try:
                unsummarized = self.get_unsummarized_messages(conv_file)
                if unsummarized:
                    print(f"  {conv_file.name}: {len(unsummarized)} messages need summarization")
                    all_unsummarized.extend(unsummarized)
            except Exception as e:
                print(f"  Error processing {conv_file.name}: {e}")

        # Clear pending files
        self.pending_files.clear()

        if not all_unsummarized:
            print("  No messages need summarization")
            return

        # Batch summarization
        total_updated = 0
        batch_size = 20

        for i in range(0, len(all_unsummarized), batch_size):
            batch = all_unsummarized[i:i+batch_size]
            print(f"  Calling Haiku to summarize batch of {len(batch)} messages...")

            summaries = self.summarizer.summarize_batch(batch)

            if summaries:
                updated = self.summarizer.update_database(summaries)
                total_updated += updated
                print(f"    ✓ Updated {updated} summaries")
            else:
                print(f"    ✗ No summaries generated")

        print(f"  ✓ Total: {total_updated} message summaries updated")
        self.last_process_time = time.time()


def ensure_indexed():
    """Index recently modified conversations to catch up after watcher downtime"""
    from claude_finder.core.indexer import ConversationIndexer

    print("Catching up on recently modified conversations...")
    try:
        indexer = ConversationIndexer()

        # Only index conversations modified in the last hour (catchup window)
        files = indexer.scan_conversations(days_back=None)

        # Filter to only files modified in last hour
        import time
        cutoff = time.time() - 3600  # 1 hour ago
        recent_files = [f for f in files if f.stat().st_mtime > cutoff]

        if recent_files:
            print(f"  Indexing {len(recent_files)} recently modified conversations...")
            import sys, io
            for conv_file in recent_files:
                try:
                    # Suppress verbose indexer output
                    old_stdout = sys.stdout
                    sys.stdout = io.StringIO()
                    try:
                        indexer.index_conversation(conv_file, summarize=False)
                    finally:
                        sys.stdout = old_stdout
                except Exception as e:
                    print(f"  Error indexing {conv_file.name}: {e}")
            print("✓ Catchup indexing complete")
        else:
            print("✓ No recent conversations to catch up on")

        indexer.close()

    except Exception as e:
        print(f"Error during catchup: {e}")


def start_watcher(verbose: bool = False, db_path: Path = None):
    """Start the file watcher daemon"""
    print("Claude Finder Watcher Daemon")
    print("=" * 50)

    # Setup
    if db_path is None:
        db_path = Path.home() / ".claude-finder" / "index.db"
    projects_dir = Path.home() / ".claude" / "projects"

    if not db_path.exists():
        print("Error: Database not found. Run 'claude-finder init' first")
        sys.exit(1)

    if not projects_dir.exists():
        print(f"Error: Claude projects directory not found: {projects_dir}")
        sys.exit(1)

    # Run initial indexing
    ensure_indexed()

    # Setup file watcher
    print(f"\nWatching: {projects_dir}")
    print("Idle timeout: 30 seconds (processes when no new changes for 30s)")
    if verbose:
        print("Verbose mode: ON (will print file changes as they happen)")
    print("Press Ctrl+C to stop\n")

    event_handler = ConversationWatcher(db_path, batch_size=10, verbose=verbose)
    observer = Observer()
    observer.schedule(event_handler, str(projects_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(5)

            # Process if: pending files exist AND no new changes for idle_threshold seconds
            if event_handler.pending_files:
                time_since_last_change = time.time() - event_handler.last_change_time
                if time_since_last_change >= event_handler.idle_threshold:
                    event_handler.process_pending()

    except KeyboardInterrupt:
        print("\nStopping watcher...")
        observer.stop()

    observer.join()
    print("✓ Watcher stopped")
