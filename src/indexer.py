#!/usr/bin/env python3
"""
Claude Finder Indexer
Scans ~/.claude/projects and indexes conversations with Haiku-generated summaries
"""

import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class ConversationIndexer:
    def __init__(self, db_path: str = "~/.claude-finder/index.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._anthropic_client = None  # Lazy-loaded when needed

    def _init_db(self):
        """Initialize database with schema"""
        schema_path = Path(__file__).parent.parent / "schema.sql"
        with open(schema_path) as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def _get_anthropic_client(self):
        """Lazy-load Anthropic client with API key"""
        if self._anthropic_client is not None:
            return self._anthropic_client

        try:
            import anthropic
        except ImportError:
            return None

        # Try to get API key from multiple sources
        api_key = None

        # 1. Environment variable
        api_key = os.environ.get('ANTHROPIC_API_KEY')

        # 2. Config file
        if not api_key:
            config_path = Path.home() / ".claude-finder" / "config.json"
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        api_key = config.get('anthropic_api_key')
                except:
                    pass

        # 3. User's shell profile (if set)
        if not api_key:
            try:
                # Try reading from shell config
                anthropic_key_file = Path.home() / ".anthropic_key"
                if anthropic_key_file.exists():
                    with open(anthropic_key_file) as f:
                        api_key = f.read().strip()
            except:
                pass

        if not api_key:
            return None

        try:
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
            return self._anthropic_client
        except Exception as e:
            print(f"  Warning: Error creating Anthropic client: {e}")
            return None

    def scan_conversations(self, days_back: Optional[int] = 1) -> List[Path]:
        """
        Scan ~/.claude/projects for conversation files

        Args:
            days_back: Only index conversations from the last N days (None = all)

        Returns:
            List of paths to JSONL files
        """
        projects_dir = Path.home() / ".claude" / "projects"
        if not projects_dir.exists():
            print(f"Projects directory not found: {projects_dir}")
            return []

        cutoff_time = None
        if days_back is not None:
            cutoff_time = datetime.now() - timedelta(days=days_back)

        conversation_files = []

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            for conv_file in project_dir.glob("*.jsonl"):
                # Skip agent files
                if conv_file.stem.startswith("agent-"):
                    continue

                # Check modification time
                if cutoff_time:
                    mtime = datetime.fromtimestamp(conv_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        continue

                conversation_files.append(conv_file)

        return sorted(conversation_files, key=lambda p: p.stat().st_mtime, reverse=True)

    def parse_conversation_file(self, file_path: Path) -> Tuple[Dict, List[Dict]]:
        """
        Parse a conversation JSONL file

        Returns:
            (conversation_metadata, messages_list)
        """
        messages = []
        conversation_meta = None

        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())

                    # First line is the summary
                    if line_num == 1 and data.get('type') == 'summary':
                        conversation_meta = data
                        continue

                    # Parse message entries
                    if 'uuid' in data and 'message' in data:
                        message_type = data.get('type', 'unknown')
                        if message_type not in ('user', 'assistant'):
                            continue

                        # Extract content
                        msg_content = data['message'].get('content', '')
                        if isinstance(msg_content, list):
                            # Flatten content blocks
                            text_parts = []
                            for block in msg_content:
                                if isinstance(block, dict):
                                    if block.get('type') == 'text':
                                        text_parts.append(block.get('text', ''))
                                    elif block.get('type') == 'thinking':
                                        # Skip thinking blocks for summaries
                                        continue
                                    elif block.get('type') == 'tool_use':
                                        tool_name = block.get('name', 'unknown')
                                        text_parts.append(f"[Tool: {tool_name}]")
                                    elif block.get('type') == 'tool_result':
                                        text_parts.append("[Tool result]")
                            msg_content = '\n'.join(text_parts)

                        messages.append({
                            'uuid': data['uuid'],
                            'parent_uuid': data.get('parentUuid'),
                            'is_sidechain': data.get('isSidechain', False),
                            'timestamp': data.get('timestamp'),
                            'message_type': message_type,
                            'content': msg_content,
                            'session_id': data.get('sessionId'),
                        })

                except json.JSONDecodeError as e:
                    print(f"Error parsing line {line_num} in {file_path}: {e}")
                    continue

        return conversation_meta, messages

    def summarize_message(self, message: Dict) -> str:
        """
        Use Haiku to generate a 1-2 sentence summary of a message
        """
        content = message['content']
        message_type = message['message_type']

        # Don't summarize very short messages
        if len(content) < 50:
            return content[:100]

        # Truncate very long messages for summarization (Haiku context limit)
        content_snippet = content[:3000]

        # Try to use Haiku via Anthropic API
        client = self._get_anthropic_client()

        if client is None:
            # Fallback: use first 150 chars
            return content[:147] + "..." if len(content) > 150 else content

        prompt = f"""Summarize this {message_type} message in 1-2 concise sentences (max 150 chars). Focus on the main action, question, or response.

Message:
{content_snippet}

Summary:"""

        try:
            response = client.messages.create(
                model="claude-haiku-4-20250514",
                max_tokens=100,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            summary = response.content[0].text.strip()

            # Ensure it's not too long
            if len(summary) > 200:
                summary = summary[:197] + "..."

            return summary

        except Exception as e:
            print(f"  Warning: Haiku summarization failed: {e}")
            # Fallback
            return content[:147] + "..." if len(content) > 150 else content

    def calculate_depth(self, messages: List[Dict], parent_map: Dict[str, str]) -> Dict[str, int]:
        """Calculate depth of each message from root"""
        depths = {}

        # Find roots (messages with no parent)
        roots = [m['uuid'] for m in messages if not m['parent_uuid']]

        # BFS to calculate depths
        queue = [(root_uuid, 0) for root_uuid in roots]
        while queue:
            uuid, depth = queue.pop(0)
            depths[uuid] = depth

            # Find children
            children = [m['uuid'] for m in messages if m['parent_uuid'] == uuid]
            for child_uuid in children:
                queue.append((child_uuid, depth + 1))

        return depths

    def index_conversation(self, file_path: Path, summarize: bool = True):
        """Index a single conversation file"""
        print(f"Indexing: {file_path}")

        # Parse file
        conv_meta, messages = self.parse_conversation_file(file_path)

        if not messages:
            print(f"  No messages found in {file_path}")
            return

        # Extract project path from file location
        project_path = file_path.parent.name.replace('-', '/')

        # Get session ID from first message
        session_id = messages[0].get('session_id')
        if not session_id:
            print(f"  No session_id found in {file_path}")
            return

        # Calculate depths
        parent_map = {m['uuid']: m['parent_uuid'] for m in messages}
        depths = self.calculate_depth(messages, parent_map)

        # Index conversation metadata
        cursor = self.conn.cursor()

        # Check if already indexed
        cursor.execute(
            "SELECT indexed_at FROM conversations WHERE session_id = ?",
            (session_id,)
        )
        existing = cursor.fetchone()

        if existing:
            print(f"  Already indexed at {existing['indexed_at']}, updating...")
            # TODO: Implement incremental updates
            # For now, delete and re-index
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))

        # Find root message
        root_message = next((m for m in messages if not m['parent_uuid']), messages[0])

        # Insert conversation
        cursor.execute("""
            INSERT INTO conversations (
                session_id, project_path, conversation_file,
                root_message_uuid, leaf_message_uuid, conversation_summary,
                first_message_at, last_message_at, message_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            project_path,
            str(file_path),
            root_message['uuid'],
            conv_meta.get('leafUuid') if conv_meta else None,
            conv_meta.get('summary', 'Untitled conversation') if conv_meta else None,
            messages[0]['timestamp'],
            messages[-1]['timestamp'],
            len(messages)
        ))

        # Insert messages with summaries
        for i, message in enumerate(messages):
            if summarize and i % 10 == 0:
                print(f"  Processing message {i+1}/{len(messages)}...")

            summary = self.summarize_message(message) if summarize else message['content'][:150]

            cursor.execute("""
                INSERT INTO messages (
                    message_uuid, session_id, parent_uuid, is_sidechain,
                    depth, timestamp, message_type, project_path,
                    conversation_file, summary, full_content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message['uuid'],
                session_id,
                message['parent_uuid'],
                message['is_sidechain'],
                depths.get(message['uuid'], 0),
                message['timestamp'],
                message['message_type'],
                project_path,
                str(file_path),
                summary,
                message['content']
            ))

        self.conn.commit()
        print(f"  ✓ Indexed {len(messages)} messages")

    def index_all(self, days_back: Optional[int] = 1, summarize: bool = True):
        """Index all conversations from the last N days"""
        files = self.scan_conversations(days_back)
        print(f"Found {len(files)} conversation files to index")

        for i, file_path in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}]")
            try:
                self.index_conversation(file_path, summarize=summarize)
            except Exception as e:
                print(f"  Error indexing {file_path}: {e}")
                import traceback
                traceback.print_exc()

        print(f"\n✓ Indexing complete!")

    def close(self):
        """Close database connection"""
        self.conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Index Claude Code conversations')
    parser.add_argument('--days', type=int, default=1,
                       help='Index conversations from last N days (default: 1)')
    parser.add_argument('--all', action='store_true',
                       help='Index all conversations regardless of age')
    parser.add_argument('--no-summarize', action='store_true',
                       help='Skip Haiku summarization (faster but less useful)')
    parser.add_argument('--db', default='~/.claude-finder/index.db',
                       help='Path to SQLite database')

    args = parser.parse_args()

    days_back = None if args.all else args.days
    summarize = not args.no_summarize

    indexer = ConversationIndexer(db_path=args.db)
    try:
        indexer.index_all(days_back=days_back, summarize=summarize)
    finally:
        indexer.close()


if __name__ == '__main__':
    main()
