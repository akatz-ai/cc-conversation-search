#!/usr/bin/env python3
"""
Conversation Search Indexer
Scans ~/.claude/projects and indexes conversations with batch AI summarization
"""

import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from importlib.resources import files
from conversation_search.core.summarization import (
    MessageSummarizer,
    is_summarizer_conversation,
    message_uses_conversation_search
)


@dataclass
class IndexRunResult:
    """Bounded indexing diagnostics suitable for CLI progress reporting."""

    discovered: int = 0
    candidates: int = 0
    indexed: int = 0
    unchanged: int = 0
    failed: int = 0
    truncated: bool = False
    elapsed_seconds: float = 0.0


class ConversationIndexer:
    def __init__(
        self,
        db_path: str = "~/.conversation-search/index.db",
        quiet: bool = False,
        projects_dir: Optional[Path] = None,
    ):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        self.quiet = quiet
        self.projects_dir = (
            Path(projects_dir).expanduser()
            if projects_dir is not None
            else Path.home() / ".claude" / "projects"
        )

        # Enable WAL mode for concurrent access
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout

        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self.summarizer = MessageSummarizer(db_path=str(self.db_path))

    def _init_db(self):
        """Initialize database with schema and run migrations"""
        schema_sql = files('conversation_search.data').joinpath('schema.sql').read_text()
        self.conn.executescript(schema_sql)

        # Inspect and apply every migration under one write lock so concurrent
        # CLI startup cannot race on ALTER TABLE or trigger replacement.
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            indexed_columns = {
                row['name']
                for row in self.conn.execute("PRAGMA table_info(indexed_files)")
            }
            for name, definition in (
                ('prefix_hash', 'TEXT'),
                ('is_summarizer', 'BOOLEAN DEFAULT FALSE'),
                ('meta_active', 'BOOLEAN DEFAULT FALSE'),
            ):
                if name not in indexed_columns:
                    self.conn.execute(
                        f"ALTER TABLE indexed_files ADD COLUMN {name} {definition}"
                    )

            message_columns = {
                row['name'] for row in self.conn.execute("PRAGMA table_info(messages)")
            }
            if 'is_meta_conversation' not in message_columns:
                self.conn.execute("""
                    ALTER TABLE messages
                    ADD COLUMN is_meta_conversation BOOLEAN DEFAULT FALSE
                """)
                if not self.quiet:
                    print("  Migrated database: added is_meta_conversation column")
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_is_meta_conversation
                ON messages(is_meta_conversation)
            """)

            trigger = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='messages_ad'"
            ).fetchone()
            if trigger and 'DELETE FROM message_content_fts' in (trigger['sql'] or ''):
                self.conn.execute("DROP TRIGGER IF EXISTS messages_ad")
                self.conn.execute("DROP TRIGGER IF EXISTS messages_au")
                self.conn.execute("""
                    CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
                        INSERT INTO message_content_fts(
                            message_content_fts, rowid, message_uuid, full_content
                        ) VALUES ('delete', old.rowid, old.message_uuid, old.full_content);
                    END
                """)
                self.conn.execute("""
                    CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
                        INSERT INTO message_content_fts(
                            message_content_fts, rowid, message_uuid, full_content
                        ) VALUES ('delete', old.rowid, old.message_uuid, old.full_content);
                        INSERT INTO message_content_fts(rowid, message_uuid, full_content)
                        VALUES (new.rowid, new.message_uuid, new.full_content);
                    END
                """)
                self.conn.execute(
                    "INSERT INTO message_content_fts(message_content_fts) VALUES('rebuild')"
                )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            raise

    def scan_conversations(
        self,
        days_back: Optional[int] = 1,
        changed_only: bool = False,
        deadline: Optional[float] = None,
    ) -> List[Path]:
        """Scan Claude projects for conversation files, newest first.

        When ``changed_only`` is true, size and nanosecond mtime are compared
        with ``indexed_files``. Unchanged files are not opened or parsed.
        """
        self._scan_truncated = False
        projects_dir = self.projects_dir
        if not projects_dir.exists():
            if not self.quiet:
                print(f"Projects directory not found: {projects_dir}")
            return []

        cutoff_time = None
        if days_back is not None:
            cutoff_time = datetime.now() - timedelta(days=days_back)

        indexed_state = {}
        if changed_only:
            for row in self.conn.execute(
                "SELECT file_path, size_bytes, mtime_ns FROM indexed_files"
            ):
                if deadline is not None and time.monotonic() >= deadline:
                    self._scan_truncated = True
                    return []
                indexed_state[row["file_path"]] = (row["size_bytes"], row["mtime_ns"])

        conversation_files = []

        for project_dir in projects_dir.iterdir():
            if deadline is not None and time.monotonic() >= deadline:
                self._scan_truncated = True
                break
            if not project_dir.is_dir():
                continue

            for conv_file in project_dir.glob("*.jsonl"):
                if deadline is not None and time.monotonic() >= deadline:
                    self._scan_truncated = True
                    break
                if conv_file.stem.startswith("agent-"):
                    continue

                try:
                    stat = conv_file.stat()
                except FileNotFoundError:  # A live session can rotate during scanning.
                    continue

                if cutoff_time and datetime.fromtimestamp(stat.st_mtime) < cutoff_time:
                    continue
                if changed_only and indexed_state.get(str(conv_file)) == (
                    stat.st_size,
                    stat.st_mtime_ns,
                ):
                    continue

                conversation_files.append((stat.st_mtime_ns, conv_file))

        conversation_files.sort(key=lambda item: item[0], reverse=True)
        return [path for _, path in conversation_files]

    def find_session_file(self, session_id: str) -> Optional[Path]:
        """Find an exact session file without parsing or broadly indexing history."""
        if not self.projects_dir.exists():
            return None
        filename = f"{session_id}.jsonl"
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                candidate = project_dir / filename
                if candidate.is_file():
                    return candidate
        return None

    def _file_is_unchanged(self, file_path: Path) -> bool:
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return False
        row = self.conn.execute(
            "SELECT size_bytes, mtime_ns FROM indexed_files WHERE file_path = ?",
            (str(file_path),),
        ).fetchone()
        return bool(row and row["size_bytes"] == stat.st_size and row["mtime_ns"] == stat.st_mtime_ns)

    def _record_file_state(
        self,
        file_path: Path,
        session_id: Optional[str],
        source_stat=None,
        processed_size: Optional[int] = None,
        prefix_hash: Optional[str] = None,
        is_summarizer: Optional[bool] = None,
        meta_active: Optional[bool] = None,
    ) -> None:
        stat = source_stat or file_path.stat()
        size_bytes = stat.st_size if processed_size is None else processed_size
        if prefix_hash is None:
            raise ValueError("prefix_hash must come from the pre-parse file snapshot")
        self.conn.execute("""
            INSERT INTO indexed_files(
                file_path, session_id, size_bytes, mtime_ns,
                prefix_hash, is_summarizer, meta_active
            ) VALUES (?, ?, ?, ?, ?, COALESCE(?, FALSE), COALESCE(?, FALSE))
            ON CONFLICT(file_path) DO UPDATE SET
                session_id = COALESCE(excluded.session_id, indexed_files.session_id),
                size_bytes = excluded.size_bytes,
                mtime_ns = excluded.mtime_ns,
                prefix_hash = excluded.prefix_hash,
                is_summarizer = COALESCE(?, indexed_files.is_summarizer),
                meta_active = COALESCE(?, indexed_files.meta_active),
                indexed_at = CURRENT_TIMESTAMP
        """, (
            str(file_path), session_id, size_bytes, stat.st_mtime_ns,
            prefix_hash, is_summarizer, meta_active, is_summarizer, meta_active,
        ))

    def _commit_early_state(
        self,
        file_path: Path,
        state,
        needs_reconcile: bool,
        **record_kwargs,
    ) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if needs_reconcile and state and state['session_id']:
                self.conn.execute(
                    "DELETE FROM messages WHERE session_id = ?",
                    (state['session_id'],),
                )
                self.conn.execute(
                    "DELETE FROM conversations WHERE session_id = ?",
                    (state['session_id'],),
                )
            self._record_file_state(file_path, **record_kwargs)
            self.conn.commit()
        except (sqlite3.Error, OSError, ValueError):
            self.conn.rollback()
            raise

    @staticmethod
    def _prefix_hash(file_path: Path, boundary: int) -> str:
        digest = hashlib.sha256()
        remaining = boundary
        with file_path.open('rb') as handle:
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
        if remaining:
            raise OSError(f"{file_path} changed while hashing")
        return digest.hexdigest()

    @staticmethod
    def _complete_jsonl_size(file_path: Path, source_size: int) -> int:
        """Return the byte boundary after the last complete newline."""
        if source_size == 0:
            return 0
        with file_path.open('rb') as handle:
            handle.seek(0, 2)
            readable_size = min(source_size, handle.tell())
            chunk_size = min(readable_size, 64 * 1024)
            handle.seek(readable_size - chunk_size)
            chunk = handle.read(chunk_size)
        newline = chunk.rfind(b'\n')
        return readable_size - chunk_size + newline + 1 if newline >= 0 else 0

    def parse_conversation_file(
        self,
        file_path: Path,
        start_offset: int = 0,
    ) -> Tuple[Dict, List[Dict]]:
        """Parse a full JSONL file or only bytes appended after ``start_offset``."""
        messages = []
        conversation_meta = None

        with open(file_path, 'rb') as f:
            if start_offset:
                f.seek(start_offset)
            first_line_number = 2 if start_offset else 1
            for line_num, line in enumerate(f, first_line_number):
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
                                        continue
                                    elif block.get('type') == 'tool_use':
                                        tool_name = block.get('name', 'unknown')
                                        text_parts.append(f"[Tool: {tool_name}]")
                                        # Include tool input for detection (especially for Bash commands)
                                        tool_input = block.get('input', {})
                                        if isinstance(tool_input, dict) and 'command' in tool_input:
                                            text_parts.append(tool_input['command'])
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
                    if not self.quiet:
                        print(f"Error parsing line {line_num} in {file_path}: {e}")
                    continue

        return conversation_meta, messages

    def calculate_depth(
        self,
        messages: List[Dict],
        parent_map: Dict[str, str],
        root_depths: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """Calculate depths in O(messages) time, including appended subtrees."""
        depths = {}
        message_uuids = set(parent_map)
        children = {}
        roots = []
        for message in messages:
            parent_uuid = message['parent_uuid']
            if parent_uuid in message_uuids:
                children.setdefault(parent_uuid, []).append(message['uuid'])
            else:
                roots.append(message['uuid'])

        queue = [
            (root_uuid, (root_depths or {}).get(root_uuid, 0))
            for root_uuid in roots
        ]
        position = 0
        while position < len(queue):
            uuid, depth = queue[position]
            position += 1
            depths[uuid] = depth
            queue.extend((child_uuid, depth + 1) for child_uuid in children.get(uuid, ()))

        return depths

    def _mark_ancestor_chain_to_user(self, search_message_uuid: str, msg_map: Dict, meta_uuids: set) -> None:
        """
        Walk up the message tree from a search message to the originating user message.

        Marks all messages in the ancestor chain as meta-conversations, stopping when
        we reach a user message with actual content (not tool results or infrastructure).

        Args:
            search_message_uuid: UUID of the message that uses conversation-search
            msg_map: Dictionary mapping UUID -> message for O(1) lookups
            meta_uuids: Set of marked UUIDs (mutated in place)
        """
        current_uuid = search_message_uuid
        visited = set()  # Cycle detection

        while current_uuid:
            # Safety: detect cycles
            if current_uuid in visited:
                break
            visited.add(current_uuid)

            # Safety: handle orphaned messages
            current = msg_map.get(current_uuid)
            if not current:
                break

            # Mark this message
            meta_uuids.add(current_uuid)
            current['is_meta_conversation'] = True

            # Stop at first REAL user message (not tool results/infrastructure)
            if current.get('message_type') == 'user':
                content = current.get('content', '').strip()
                # Skip system-generated user messages
                if (not content.startswith('[Tool') and
                    not content.startswith('<command-message>') and
                    not content.startswith('Base directory')):
                    break  # Found real user message

            # Continue walking up
            current_uuid = current.get('parent_uuid')

    def _mark_descendant_chain(self, search_message_uuid: str, children_map: Dict, msg_map: Dict, meta_uuids: set) -> None:
        """
        Walk down from search message to mark search results and descendants.

        Marks descendants of the search message (tool results, processing, answer) until
        we hit a real user message (indicating follow-up work) or conversation ends.

        Args:
            search_message_uuid: UUID of the message that uses conversation-search
            children_map: Dictionary mapping parent_uuid -> list of child UUIDs
            msg_map: Dictionary mapping UUID -> message for O(1) lookups
            meta_uuids: Set of marked UUIDs (mutated in place)
        """
        current_uuid = search_message_uuid
        visited = set()
        max_depth = 20  # Safety limit for downward walk

        for _ in range(max_depth):
            # Already marked this one, get children
            children = children_map.get(current_uuid, [])

            # No children = end of conversation
            if not children:
                break

            # Take first child (main chain, ignore sidechains for now)
            child_uuid = children[0]

            # Safety: detect cycles
            if child_uuid in visited:
                break
            visited.add(child_uuid)

            child = msg_map.get(child_uuid)
            if not child:
                break

            # Check if this is a real user message (stop condition)
            if child.get('message_type') == 'user':
                content = child.get('content', '').strip()
                # If it's NOT a system message, this is real follow-up work
                if (not content.startswith('[Tool') and
                    not content.startswith('<command-message>') and
                    not content.startswith('Base directory')):
                    break  # Stop before real user message

            # Mark and continue
            meta_uuids.add(child_uuid)
            child['is_meta_conversation'] = True
            current_uuid = child_uuid

    def _mark_meta_conversations(self, messages: List[Dict]) -> set:
        """
        Find and mark conversation-search usage, ancestors, and descendants as meta.

        Walks up from search messages to find originating user requests, and walks
        down to mark search results. This filters entire meta-conversation transactions
        where users ask Claude to search for past conversations and receive results.

        Args:
            messages: List of message dicts with uuid, parent_uuid, message_type, content

        Returns:
            Set of message UUIDs that are meta-conversations
        """
        meta_uuids = set()
        msg_map = {m['uuid']: m for m in messages}

        # Build children map for downward traversal
        children_map = {}
        for message in messages:
            parent_uuid = message.get('parent_uuid')
            if parent_uuid:
                if parent_uuid not in children_map:
                    children_map[parent_uuid] = []
                children_map[parent_uuid].append(message['uuid'])

        # Find all messages that use conversation-search
        for message in messages:
            if not message_uses_conversation_search(message):
                continue

            # Mark search message
            meta_uuids.add(message['uuid'])
            message['is_meta_conversation'] = True

            # Walk up to originating user message
            self._mark_ancestor_chain_to_user(message['uuid'], msg_map, meta_uuids)

            # Walk down to mark search results
            self._mark_descendant_chain(message['uuid'], children_map, msg_map, meta_uuids)

        return meta_uuids

    @staticmethod
    def _is_real_user_message(message: Dict) -> bool:
        if message.get('message_type') != 'user':
            return False
        content = message.get('content', '').strip()
        return not (
            content.startswith('[Tool')
            or content.startswith('<command-message>')
            or content.startswith('Base directory')
        )

    def _continue_meta_state(self, messages: List[Dict], active: bool) -> bool:
        """Carry meta-transaction state across incremental suffix batches."""
        for message in messages:
            if active:
                if self._is_real_user_message(message):
                    active = False
                else:
                    message['is_meta_conversation'] = True
            if message_uses_conversation_search(message):
                message['is_meta_conversation'] = True
                active = True
        return active

    def _mark_stored_ancestors(self, cursor, messages: List[Dict]) -> None:
        """Mark ancestors already stored before an appended search command."""
        for message in messages:
            if not message_uses_conversation_search(message):
                continue
            parent_uuid = message.get('parent_uuid')
            visited = set()
            while parent_uuid and parent_uuid not in visited:
                visited.add(parent_uuid)
                row = cursor.execute("""
                    SELECT message_uuid, parent_uuid, message_type, full_content
                    FROM messages WHERE message_uuid = ?
                """, (parent_uuid,)).fetchone()
                if not row:
                    break
                cursor.execute(
                    "UPDATE messages SET is_meta_conversation = TRUE WHERE message_uuid = ?",
                    (row['message_uuid'],),
                )
                stored = {
                    'message_type': row['message_type'],
                    'content': row['full_content'],
                }
                if self._is_real_user_message(stored):
                    break
                parent_uuid = row['parent_uuid']

    def index_conversation(
        self,
        file_path: Path,
        summarize: bool = True,
        force: bool = False,
    ) -> bool:
        """Index one file and always restore a usable connection on failure."""
        try:
            return self._index_conversation(file_path, summarize, force)
        except BaseException:
            self.conn.rollback()
            raise

    def _index_conversation(
        self,
        file_path: Path,
        summarize: bool = True,
        force: bool = False,
    ) -> bool:
        """Index one changed file atomically; return whether work was performed."""
        if not force and self._file_is_unchanged(file_path):
            return False
        # Capture state before reading. If a live process appends while parsing,
        # recording this older state guarantees the next run sees the change.
        source_stat = file_path.stat()
        complete_size = self._complete_jsonl_size(file_path, source_stat.st_size)
        snapshot_hash = self._prefix_hash(file_path, complete_size)
        state = self.conn.execute(
            """SELECT f.session_id, f.size_bytes, f.prefix_hash,
                      f.is_summarizer, f.meta_active,
                      (SELECT c.message_count FROM conversations c
                       WHERE c.session_id = f.session_id) AS message_count
               FROM indexed_files f WHERE f.file_path = ?""",
            (str(file_path),),
        ).fetchone()
        start_offset = 0
        needs_reconcile = bool(state)
        if state and source_stat.st_size > state['size_bytes']:
            current_prefix_hash = self._prefix_hash(file_path, state['size_bytes'])
            if state['prefix_hash'] and current_prefix_hash == state['prefix_hash']:
                start_offset = state['size_bytes']
                needs_reconcile = False

        # Empty and one-message files are not classifiable yet: summarizer
        # detection needs the user/assistant pair. Reparse the first append in full.
        if (
            state
            and not state['is_summarizer']
            and (state['message_count'] is None or state['message_count'] < 2)
        ):
            start_offset = 0
            needs_reconcile = True

        if state and state['is_summarizer'] and not needs_reconcile:
            self._commit_early_state(
                file_path, state, needs_reconcile,
                session_id=state['session_id'], source_stat=source_stat,
                processed_size=complete_size, prefix_hash=snapshot_hash,
                is_summarizer=True, meta_active=bool(state['meta_active']),
            )
            return True

        if not self.quiet:
            print(f"Indexing: {file_path}")

        # Parse only the append for a previously indexed, append-only live file.
        conv_meta, messages = self.parse_conversation_file(file_path, start_offset)

        if not messages:
            if not self.quiet:
                print(f"  No messages found in {file_path}")
            self._commit_early_state(
                file_path, state, needs_reconcile,
                session_id=None, source_stat=source_stat,
                processed_size=complete_size, prefix_hash=snapshot_hash,
                is_summarizer=False,
                meta_active=bool(state['meta_active']) if state else False,
            )
            return True

        # File-global summarizer classification is only valid after a full parse.
        # A normal session's appended suffix can contain the same heuristic words.
        if (not state or needs_reconcile) and is_summarizer_conversation(file_path, messages):
            if not self.quiet:
                print(f"  ⏭️  Skipping automated summarizer conversation")
            self._commit_early_state(
                file_path, state, needs_reconcile,
                session_id=messages[0].get('session_id'),
                source_stat=source_stat, processed_size=complete_size,
                prefix_hash=snapshot_hash, is_summarizer=True,
                meta_active=False,
            )
            return True

        # Mark meta-conversations (search pairs), carrying an in-progress search
        # transaction across append batches.
        meta_active = self._continue_meta_state(
            messages, bool(state['meta_active']) if state and start_offset else False
        )
        meta_uuids = self._mark_meta_conversations(messages)
        if meta_uuids and not self.quiet:
            pair_count = len(meta_uuids) // 2  # Approximate number of pairs
            print(f"  🏷️  Marking {len(meta_uuids)} meta-search messages (~{pair_count} pairs)")

        # Extract project path from file location
        project_path = file_path.parent.name.replace('-', '/')

        # Get session ID from first message
        session_id = messages[0].get('session_id')
        if not session_id:
            if not self.quiet:
                print(f"  No session_id found in {file_path}")
            self._commit_early_state(
                file_path, state, needs_reconcile,
                session_id=None, source_stat=source_stat,
                processed_size=complete_size, prefix_hash=snapshot_hash,
                is_summarizer=False, meta_active=meta_active,
            )
            return True

        # Calculate depths. Appended messages can have parents already in SQLite.
        parent_map = {m['uuid']: m['parent_uuid'] for m in messages}
        message_uuids = set(parent_map)
        external_parents = {
            parent for parent in parent_map.values()
            if parent and parent not in message_uuids
        }
        existing_depths = {}
        if external_parents:
            placeholders = ','.join('?' for _ in external_parents)
            rows = self.conn.execute(
                f"SELECT message_uuid, depth FROM messages WHERE message_uuid IN ({placeholders})",
                tuple(external_parents),
            )
            parent_depths = {row['message_uuid']: row['depth'] for row in rows}
            existing_depths = {
                uuid: parent_depths[parent] + 1
                for uuid, parent in parent_map.items()
                if parent in parent_depths
            }
        depths = self.calculate_depth(messages, parent_map, existing_depths)

        # Serialize the read/insert sequence across concurrent CLI processes. This
        # prevents two searches from racing between the existence check and insert.
        self.conn.execute("BEGIN IMMEDIATE")
        cursor = self.conn.cursor()

        if needs_reconcile and state and state['session_id']:
            cursor.execute(
                "DELETE FROM messages WHERE session_id = ?", (state['session_id'],)
            )
            cursor.execute(
                "DELETE FROM conversations WHERE session_id = ?", (state['session_id'],)
            )

        # Searches appended after their user prompt must also hide ancestors that
        # were indexed in a previous batch.
        self._mark_stored_ancestors(cursor, messages)

        # Check if already indexed
        cursor.execute(
            "SELECT indexed_at FROM conversations WHERE session_id = ?",
            (session_id,)
        )
        existing = cursor.fetchone()

        is_update = False
        if existing:
            if not self.quiet:
                print(f"  Already indexed at {existing['indexed_at']}, checking for new messages...")

            # Get existing message UUIDs
            cursor.execute(
                "SELECT message_uuid FROM messages WHERE session_id = ?",
                (session_id,)
            )
            existing_uuids = {row['message_uuid'] for row in cursor.fetchall()}

            # Find new messages only
            new_messages = [m for m in messages if m['uuid'] not in existing_uuids]

            if not new_messages:
                if not self.quiet:
                    print(f"  No new messages, skipping")
                self._record_file_state(
                    file_path, session_id, source_stat,
                    processed_size=complete_size, prefix_hash=snapshot_hash,
                    is_summarizer=False, meta_active=meta_active,
                )
                self.conn.commit()
                return True

            if not self.quiet:
                print(f"  Found {len(new_messages)} new messages (total: {len(messages)})")

            # Save reference to all messages for metadata update
            all_messages = messages
            messages = new_messages  # Only process new ones
            is_update = True

            # Update conversation metadata (use last message from ALL messages, not just new ones)
            cursor.execute("""
                UPDATE conversations
                SET last_message_at = ?,
                    message_count = ?,
                    leaf_message_uuid = COALESCE(?, leaf_message_uuid),
                    indexed_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (
                all_messages[-1]['timestamp'],
                len(existing_uuids) + len(new_messages),
                conv_meta.get('leafUuid') if conv_meta else None,
                session_id
            ))
        else:
            # New conversation - insert metadata
            root_message = next((m for m in messages if not m['parent_uuid']), messages[0])

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

        # Classify messages for tool noise filtering
        tool_noise_uuids = []
        for message in messages:
            if self.summarizer.is_tool_noise(message):
                tool_noise_uuids.append(message['uuid'])

        # Insert all messages in a single transaction
        try:
            inserted_count = 0
            for message in messages:
                cursor.execute("""
                    INSERT OR IGNORE INTO messages (
                        message_uuid, session_id, parent_uuid, is_sidechain,
                        depth, timestamp, message_type, project_path,
                        conversation_file, full_content, is_meta_conversation,
                        is_tool_noise
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    message['content'],
                    message.get('is_meta_conversation', False),
                    message['uuid'] in tool_noise_uuids
                ))
                inserted_count += cursor.rowcount

            # A UUID can be repeated in imported/branched logs. The global UUID
            # remains the public lookup key, so retain the first copy idempotently.
            # Recompute metadata from rows actually owned by this session.
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            )
            stored_count = cursor.fetchone()[0]
            cursor.execute("""
                UPDATE conversations
                SET message_count = ?, indexed_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (stored_count, session_id))
            self._record_file_state(
                file_path, session_id, source_stat,
                processed_size=complete_size, prefix_hash=snapshot_hash,
                is_summarizer=False, meta_active=meta_active,
            )

            # Commit once at the end
            self.conn.commit()

            if tool_noise_uuids and not self.quiet:
                print(f"  Marked {len(tool_noise_uuids)} messages as tool noise")

            if not self.quiet:
                if is_update:
                    print(f"  ✓ Added {inserted_count} new messages")
                else:
                    print(f"  ✓ Indexed {inserted_count} messages")
            return True

        except (sqlite3.Error, OSError) as e:
            self.conn.rollback()
            if not self.quiet:
                print(f"  Error during indexing, rolled back: {e}")
            raise

    def index_changed(
        self,
        days_back: Optional[int] = 30,
        max_files: Optional[int] = 200,
        timeout_seconds: Optional[float] = 5.0,
    ) -> IndexRunResult:
        """Index only changed files within explicit file and wall-clock budgets."""
        started = time.monotonic()
        deadline = started + timeout_seconds if timeout_seconds is not None else None
        files = self.scan_conversations(
            days_back, changed_only=True, deadline=deadline
        )
        result = IndexRunResult(
            discovered=len(files),
            candidates=len(files),
            truncated=self._scan_truncated,
        )

        for position, file_path in enumerate(files):
            if max_files is not None and position >= max_files:
                result.truncated = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                result.truncated = True
                break
            try:
                if self.index_conversation(file_path, summarize=True):
                    result.indexed += 1
                else:
                    result.unchanged += 1
            except (OSError, sqlite3.Error, ValueError) as exc:
                result.failed += 1
                if not self.quiet:
                    print(f"  Error indexing {file_path.name}: {exc}", file=sys.stderr)

        result.elapsed_seconds = time.monotonic() - started
        return result

    def index_all(self, days_back: Optional[int] = 1, summarize: bool = True):
        """Index all conversations from the last N days"""
        files = self.scan_conversations(days_back)
        if not self.quiet:
            print(f"Found {len(files)} conversation files to index")

        for i, file_path in enumerate(files, 1):
            if not self.quiet:
                print(f"\n[{i}/{len(files)}]")
            try:
                self.index_conversation(file_path, summarize=summarize)
            except Exception as e:
                if not self.quiet:
                    print(f"  Error indexing {file_path}: {e}")
                    import traceback
                    traceback.print_exc()

        if not self.quiet:
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
    parser.add_argument('--no-extract', action='store_true',
                       help='Skip smart extraction (store only raw content)')
    parser.add_argument('--db', default='~/.conversation-search/index.db',
                       help='Path to SQLite database')

    args = parser.parse_args()

    days_back = None if args.all else args.days
    extract = not args.no_extract

    indexer = ConversationIndexer(db_path=args.db)
    try:
        indexer.index_all(days_back=days_back, summarize=extract)
    finally:
        indexer.close()


if __name__ == '__main__':
    main()
