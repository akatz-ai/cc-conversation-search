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


class ConversationWatcher(FileSystemEventHandler):
    """Watches conversation files and tracks unsummarized messages"""

    def __init__(self, db_path: Path, batch_size: int = 10):
        self.db_path = db_path
        self.batch_size = batch_size
        self.pending_files: Set[Path] = set()
        self.last_process_time = time.time()
        self.min_batch_interval = 30  # Wait at least 30s between batches

    def on_modified(self, event):
        """Called when a file is modified"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only watch .jsonl conversation files (not agent files)
        if file_path.suffix == '.jsonl' and not file_path.stem.startswith('agent-'):
            self.pending_files.add(file_path)

            # Check if we should process now
            time_since_last = time.time() - self.last_process_time
            if time_since_last >= self.min_batch_interval:
                self.process_pending()

    def get_unsummarized_messages(self, conv_file: Path) -> List[Dict]:
        """
        Get messages from a conversation file that don't have summaries yet

        A message needs summarization if:
        1. It exists in the DB (has been indexed)
        2. Its summary is just truncated content (not AI-generated)
        """
        conn = sqlite3.connect(str(self.db_path))
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
        # A message needs summarization if its summary is truncated content
        unsummarized = []

        for msg in file_messages:
            cursor.execute("""
                SELECT message_uuid, summary, full_content
                FROM messages
                WHERE message_uuid = ?
            """, (msg['uuid'],))

            result = cursor.fetchone()

            if result:
                summary = result['summary']
                full_content = result['full_content']

                # Check if summary is just truncated content (needs AI summary)
                # Heuristic: if summary is exactly first 147 chars + "..." or similar
                is_truncated = (
                    summary.endswith('...') and
                    len(summary) >= 140 and
                    full_content.startswith(summary[:-3].strip())
                )

                if is_truncated:
                    unsummarized.append(msg)

        conn.close()
        return unsummarized

    def call_haiku_summarizer(self, messages: List[Dict]) -> Dict:
        """Call Claude CLI with Haiku to generate summaries"""
        messages_json = json.dumps([{
            'uuid': m['uuid'],
            'message_type': m['message_type'],
            'content': m['content'][:2000]
        } for m in messages], indent=2)

        prompt = f"""You are a summarization assistant. Generate concise summaries for conversation messages.

Messages to summarize:
{messages_json}

For each message, create a 1-2 sentence summary (max 150 characters) that captures the main point.
- For user messages: capture the question, request, or action
- For assistant messages: capture the key action, answer, or explanation
- Use active voice and clear language

Output ONLY valid JSON in this exact format:
{{
  "summaries": [
    {{"uuid": "message-uuid", "message_type": "user|assistant", "summary": "Brief summary here"}},
    ...
  ]
}}

JSON output:"""

        try:
            result = subprocess.run(
                ['claude', '--model', 'haiku'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"Error calling Claude: {result.stderr}", file=sys.stderr)
                return {"summaries": []}

            output = result.stdout.strip()

            # Extract JSON
            json_start = output.find('{')
            json_end = output.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                return json.loads(json_str)
            else:
                return {"summaries": []}

        except Exception as e:
            print(f"Error calling Haiku: {e}", file=sys.stderr)
            return {"summaries": []}

    def update_summaries(self, summaries: List[Dict]) -> int:
        """Update database with new summaries"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        updated = 0
        for summary_data in summaries:
            uuid = summary_data.get('uuid')
            summary = summary_data.get('summary')

            if not uuid or not summary:
                continue

            cursor.execute("""
                UPDATE messages
                SET summary = ?
                WHERE message_uuid = ?
            """, (summary, uuid))

            if cursor.rowcount > 0:
                updated += 1

        conn.commit()
        conn.close()

        return updated

    def process_pending(self):
        """Process pending files and summarize messages"""
        if not self.pending_files:
            return

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing {len(self.pending_files)} updated conversations...")

        all_unsummarized = []

        # Collect unsummarized messages from all pending files
        for conv_file in list(self.pending_files):
            if not conv_file.exists():
                self.pending_files.remove(conv_file)
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
        batch_size = 20  # Process 20 messages at a time

        for i in range(0, len(all_unsummarized), batch_size):
            batch = all_unsummarized[i:i+batch_size]
            print(f"  Calling Haiku to summarize batch of {len(batch)} messages...")

            result = self.call_haiku_summarizer(batch)
            summaries = result.get('summaries', [])

            if summaries:
                updated = self.update_summaries(summaries)
                total_updated += updated
                print(f"    ✓ Updated {updated} summaries")
            else:
                print(f"    ✗ No summaries generated")

        print(f"  ✓ Total: {total_updated} message summaries updated")
        self.last_process_time = time.time()


def ensure_indexed():
    """Run the indexer to ensure all messages are in the DB"""
    script_dir = Path(__file__).parent
    indexer = script_dir / "indexer.py"

    print("Running initial indexing (without summaries)...")
    try:
        result = subprocess.run(
            [sys.executable, str(indexer), '--days', '1', '--no-summarize'],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            print("✓ Initial indexing complete")
        else:
            print(f"Warning: Indexer had issues:\n{result.stderr}")

    except Exception as e:
        print(f"Error running indexer: {e}")


def main():
    print("Claude Finder Watcher Daemon")
    print("=" * 50)

    # Setup
    db_path = Path.home() / ".claude-finder" / "index.db"
    projects_dir = Path.home() / ".claude" / "projects"

    if not db_path.exists():
        print("Error: Database not found. Run indexer first:")
        print("  python3 src/indexer.py --days 7")
        sys.exit(1)

    if not projects_dir.exists():
        print(f"Error: Claude projects directory not found: {projects_dir}")
        sys.exit(1)

    # Run initial indexing
    ensure_indexed()

    # Setup file watcher
    print(f"\nWatching: {projects_dir}")
    print("Batch size: 10 messages (or 30s delay)")
    print("Press Ctrl+C to stop\n")

    event_handler = ConversationWatcher(db_path, batch_size=10)
    observer = Observer()
    observer.schedule(event_handler, str(projects_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(5)

            # Periodically process if enough time has passed
            if event_handler.pending_files:
                time_since_last = time.time() - event_handler.last_process_time
                if time_since_last >= event_handler.min_batch_interval:
                    event_handler.process_pending()

    except KeyboardInterrupt:
        print("\nStopping watcher...")
        observer.stop()

    observer.join()
    print("✓ Watcher stopped")


if __name__ == '__main__':
    main()
