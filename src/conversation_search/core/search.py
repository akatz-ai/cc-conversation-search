#!/usr/bin/env python3
"""
Conversation Search Search Tools
Provides search and retrieval tools for Claude to query conversation history
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from conversation_search.core.summarization import MessageSummarizer
from conversation_search.core.date_utils import build_date_filter


def format_timestamp(iso_timestamp: str, include_date: bool = True, include_seconds: bool = False) -> str:
    """
    Convert UTC ISO timestamp to local time for display.

    Args:
        iso_timestamp: ISO format timestamp with Z suffix (UTC)
        include_date: Include date in output (default: True)
        include_seconds: Include seconds in time (default: False)

    Returns:
        Formatted timestamp in local timezone
    """
    dt_utc = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
    dt_local = dt_utc.astimezone()

    if include_date:
        if include_seconds:
            return dt_local.strftime('%Y-%m-%d %H:%M:%S')
        else:
            return dt_local.strftime('%Y-%m-%d %H:%M')
    else:
        if include_seconds:
            return dt_local.strftime('%H:%M:%S')
        else:
            return dt_local.strftime('%H:%M')


class ConversationSearch:
    def __init__(self, db_path: str = "~/.conversation-search/index.db"):
        self.db_path = Path(db_path).expanduser()
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found at {self.db_path}. "
                "Run the indexer first: python src/indexer.py"
            )
        self.conn = sqlite3.connect(str(self.db_path), timeout=30.0)

        # Enable WAL mode for concurrent access
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout

        self.conn.row_factory = sqlite3.Row
        self._fts_rebuilt = False

    def search_conversations(
        self,
        query: str,
        days_back: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 20,
        project_path: Optional[str] = None,
        snippet_tokens: int = 128
    ) -> List[Dict]:
        """
        Search conversations using full-text search on complete content

        Args:
            query: Search query
            days_back: Limit to last N days (None = all time)
            since: Start date (YYYY-MM-DD, 'yesterday', 'today')
            until: End date (YYYY-MM-DD, 'yesterday', 'today')
            date: Specific date (YYYY-MM-DD, 'yesterday', 'today')
            limit: Maximum number of results
            project_path: Filter by project path
            snippet_tokens: Number of tokens to show around each match (default: 128)

        Returns:
            List of matching messages with context snippets
        """
        # Validate mutually exclusive date filters
        if days_back and (since or until or date):
            raise ValueError("Cannot use --days with --since/--until/--date")
        cursor = self.conn.cursor()

        # Handle empty query (match all)
        if not query or not query.strip():
            # No FTS search, just filter by dates/project
            sql = """
                SELECT
                    m.message_uuid,
                    m.session_id,
                    m.parent_uuid,
                    m.timestamp,
                    m.message_type,
                    m.project_path,
                    m.depth,
                    m.is_sidechain,
                    SUBSTR(m.full_content, 1, 500) as context_snippet,
                    c.conversation_summary,
                    c.conversation_file
                FROM messages m
                JOIN conversations c ON m.session_id = c.session_id
                WHERE m.is_meta_conversation = FALSE
            """
            params = []
        else:
            # Sanitize query for FTS5
            fts_query = query
            if not any(op in query for op in [' AND ', ' OR ', ' NOT ', '"']):
                terms = query.split()
                if len(terms) == 1:
                    fts_query = f'{terms[0]}*'
                else:
                    fts_query = ' '.join(f'{term}*' for term in terms)

            sql = """
                SELECT
                    m.message_uuid,
                    m.session_id,
                    m.parent_uuid,
                    m.timestamp,
                    m.message_type,
                    m.project_path,
                    m.depth,
                    m.is_sidechain,
                    snippet(message_content_fts, 1, '**', '**', '...', ?) as context_snippet,
                    c.conversation_summary,
                    c.conversation_file
                FROM messages m
                JOIN message_content_fts ON m.rowid = message_content_fts.rowid
                JOIN conversations c ON m.session_id = c.session_id
                WHERE message_content_fts.full_content MATCH ?
                  AND m.is_meta_conversation = FALSE
            """
            params = [snippet_tokens, fts_query]

        # Date filtering: use date range if provided, else days_back
        if date or since or until:
            date_sql, date_params = build_date_filter(since, until, date)
            if date_sql:
                sql += f" AND m.{date_sql}"
                params.extend(date_params)
        elif days_back:
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            sql += " AND m.timestamp >= ?"
            params.append(cutoff)

        if project_path:
            sql += " AND m.project_path = ?"
            params.append(project_path)

        sql += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            # Handle FTS corruption
            if 'fts5: missing row' in str(e) and not self._fts_rebuilt:
                print("FTS index corruption detected, rebuilding...", file=sys.stderr)
                self._rebuild_fts()
                print("FTS index rebuilt, retrying search...", file=sys.stderr)
                # Retry once
                cursor.execute(sql, params)
                results = cursor.fetchall()
                return [dict(row) for row in results]
            raise

    def get_conversation_context(
        self,
        message_uuid: str,
        depth: int = 3,
        include_children: bool = False
    ) -> Dict:
        """
        Get contextual messages around a specific message (progressive disclosure)

        Args:
            message_uuid: The message to get context for
            depth: How many parent levels to include
            include_children: Whether to include child messages (branches)

        Returns:
            Dict with the message, ancestors, and optionally children
        """
        cursor = self.conn.cursor()

        # Get the target message
        cursor.execute("""
            SELECT * FROM messages WHERE message_uuid = ?
        """, (message_uuid,))
        target = cursor.fetchone()

        if not target:
            return {"error": f"Message {message_uuid} not found"}

        target_dict = dict(target)

        # Get ancestors (walking up the tree)
        ancestors = []
        current_uuid = target_dict['parent_uuid']
        levels = 0

        while current_uuid and levels < depth:
            cursor.execute("""
                SELECT * FROM messages WHERE message_uuid = ?
            """, (current_uuid,))
            parent = cursor.fetchone()

            if not parent:
                break

            ancestors.insert(0, dict(parent))
            current_uuid = parent['parent_uuid']
            levels += 1

        # Get children (branches from this message)
        children = []
        if include_children:
            cursor.execute("""
                SELECT * FROM messages
                WHERE parent_uuid = ?
                ORDER BY timestamp ASC
            """, (message_uuid,))
            children = [dict(row) for row in cursor.fetchall()]

        # Get conversation metadata
        cursor.execute("""
            SELECT * FROM conversations WHERE session_id = ?
        """, (target_dict['session_id'],))
        conversation = dict(cursor.fetchone())

        return {
            "message": target_dict,
            "ancestors": ancestors,
            "children": children,
            "conversation": conversation,
            "context_depth": len(ancestors)
        }

    def get_conversation_tree(self, session_id: str) -> Dict:
        """
        Get the full conversation tree for a session

        Returns:
            Tree structure with all messages
        """
        cursor = self.conn.cursor()

        # Get all messages
        cursor.execute("""
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        messages = [dict(row) for row in cursor.fetchall()]

        # Get conversation metadata
        cursor.execute("""
            SELECT * FROM conversations WHERE session_id = ?
        """, (session_id,))
        conversation = cursor.fetchone()

        if not conversation:
            return {"error": f"Conversation {session_id} not found"}

        # Build tree structure
        tree = self._build_tree(messages)

        return {
            "conversation": dict(conversation),
            "tree": tree,
            "total_messages": len(messages)
        }

    def _build_tree(self, messages: List[Dict]) -> List[Dict]:
        """Build a tree structure from flat message list"""
        # Create a map of uuid -> message
        msg_map = {m['message_uuid']: {**m, 'children': []} for m in messages}

        # Build the tree
        roots = []
        for msg in msg_map.values():
            parent_uuid = msg.get('parent_uuid')
            if parent_uuid and parent_uuid in msg_map:
                msg_map[parent_uuid]['children'].append(msg)
            else:
                roots.append(msg)

        return roots

    def list_recent_conversations(
        self,
        days_back: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 20,
        project_path: Optional[str] = None
    ) -> List[Dict]:
        """
        List recent conversations

        Args:
            days_back: Limit to last N days (default: 7 if no other filters)
            since: Start date (YYYY-MM-DD, 'yesterday', 'today')
            until: End date (YYYY-MM-DD, 'yesterday', 'today')
            date: Specific date (YYYY-MM-DD, 'yesterday', 'today')
            limit: Maximum results
            project_path: Filter by project path

        Returns:
            List of conversation metadata
        """
        # Default to 7 days if no filters provided
        if days_back is None and not (since or until or date):
            days_back = 7

        # Validate mutually exclusive date filters
        if days_back and (since or until or date):
            raise ValueError("Cannot use --days with --since/--until/--date")

        cursor = self.conn.cursor()

        sql = """
            SELECT * FROM conversations
            WHERE 1=1
        """
        params = []

        # Date filtering
        if date or since or until:
            date_sql, date_params = build_date_filter(since, until, date)
            if date_sql:
                sql += f" AND {date_sql.replace('timestamp', 'last_message_at')}"
                params.extend(date_params)
        elif days_back:
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            sql += " AND last_message_at >= ?"
            params.append(cutoff)

        if project_path:
            sql += " AND project_path = ?"
            params.append(project_path)

        sql += " ORDER BY last_message_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_full_message_content(self, message_uuid: str) -> Optional[str]:
        """Get the full content of a message (not just summary)"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT full_content FROM messages WHERE message_uuid = ?
        """, (message_uuid,))
        result = cursor.fetchone()
        return result['full_content'] if result else None

    def get_full_messages(self, uuids: List[str]) -> List[Dict]:
        """Batch fetch full content for multiple messages. Supports UUID prefixes."""
        if not uuids:
            return []

        cursor = self.conn.cursor()
        results = []

        for uuid in uuids:
            # If it's a short UUID (8 chars), use prefix matching
            if len(uuid) <= 8:
                cursor.execute("""
                    SELECT message_uuid, full_content, timestamp, message_type,
                           project_path, summary
                    FROM messages
                    WHERE message_uuid LIKE ?
                    ORDER BY timestamp
                    LIMIT 1
                """, (f"{uuid}%",))
            else:
                # Full UUID
                cursor.execute("""
                    SELECT message_uuid, full_content, timestamp, message_type,
                           project_path, summary
                    FROM messages
                    WHERE message_uuid = ?
                """, (uuid,))

            row = cursor.fetchone()
            if row:
                results.append(dict(row))

        return results

    def load_context(
        self,
        days_back: int = 1,
        project_path: Optional[str] = None,
        max_conversations: int = 10,
        max_messages_per_conv: int = 50
    ) -> str:
        """
        Load recent conversation context for Claude to read directly.
        Returns token-efficient formatted text.
        """
        cursor = self.conn.cursor()

        # Get recent conversations
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
        sql = """
            SELECT session_id, conversation_summary, project_path,
                   message_count, last_message_at
            FROM conversations
            WHERE last_message_at >= ?
                AND conversation_summary IS NOT NULL
                AND conversation_summary != 'None'
                AND message_count > 2
        """
        params = [cutoff]

        # Filter out daemon internal conversations (Haiku summarization calls)
        sql += " AND NOT (project_path LIKE '%claude/finder' AND message_count < 5)"

        if project_path:
            sql += " AND project_path = ?"
            params.append(project_path)

        sql += " ORDER BY last_message_at DESC LIMIT ?"
        params.append(max_conversations)

        cursor.execute(sql, params)
        conversations = [dict(row) for row in cursor.fetchall()]

        if not conversations:
            return f"No conversations found in the last {days_back} day(s)."

        # Build output
        lines = [f"# Conversations (last {days_back} day{'s' if days_back != 1 else ''})\n"]

        for conv in conversations:
            # Get messages for this conversation
            cursor.execute("""
                SELECT message_uuid, timestamp, message_type, summary,
                       is_sidechain, project_path, is_tool_noise
                FROM messages
                WHERE session_id = ? AND is_tool_noise = FALSE AND is_meta_conversation = FALSE
                ORDER BY timestamp DESC
                LIMIT ?
            """, (conv['session_id'], max_messages_per_conv))

            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()  # Chronological order

            # Format conversation block
            dt_utc = datetime.fromisoformat(conv['last_message_at'].replace('Z', '+00:00'))
            dt_local = dt_utc.astimezone()
            date_str = dt_local.strftime('%b-%d')
            time_str = format_timestamp(conv['last_message_at'], include_date=False)
            session_short = conv['session_id'][:8]

            lines.append(f"## [{session_short}] {conv['conversation_summary']}")
            lines.append(f"**{conv['message_count']} msgs** | {conv['project_path']} | {date_str} {time_str}\n")

            # Filter and format messages compactly
            # Skip tool use/result noise, only show actual conversational content
            for msg in messages:
                summary = msg['summary'] or ""

                # Skip tool-only messages (noise)
                if (not summary or
                    summary.startswith('[Tool') or
                    summary == '[Tool result]' or
                    summary.startswith('[Request interrupted') or
                    len(summary.strip()) < 10):  # Skip very short/empty summaries
                    continue

                msg_time = format_timestamp(msg['timestamp'], include_date=False)
                icon = "👤" if msg['message_type'] == 'user' else "🤖"
                branch = "🌿 " if msg['is_sidechain'] else ""
                uuid_short = msg['message_uuid'][:8]

                lines.append(f"{icon} {msg_time} `{uuid_short}` {branch}{summary}")

            lines.append("")  # Blank line between conversations

        return "\n".join(lines)

    def _rebuild_fts(self):
        """Rebuild FTS index from scratch"""
        cursor = self.conn.cursor()

        # Use FTS5 rebuild command - this is the proper way to rebuild content tables
        cursor.execute("INSERT INTO message_content_fts(message_content_fts) VALUES('rebuild')")

        self.conn.commit()
        self._fts_rebuilt = True

    def _validate_fts(self) -> bool:
        """Check if FTS is in sync with messages table. Returns True if valid."""
        cursor = self.conn.cursor()

        try:
            # FTS5 integrity check
            cursor.execute("INSERT INTO message_content_fts(message_content_fts) VALUES('integrity-check')")
            return True
        except sqlite3.Error:
            return False

    def close(self):
        """Close database connection"""
        self.conn.close()


def format_message_for_display(msg: Dict, include_content: bool = False) -> str:
    """Format a message for human-readable display"""
    time_str = format_timestamp(msg['timestamp'])
    icon = "👤" if msg['message_type'] == 'user' else "🤖"
    branch_marker = "🌿" if msg['is_sidechain'] else ""

    lines = [
        f"{icon} {branch_marker} [{time_str}] {msg['project_path']}",
        f"   Summary: {msg['summary']}",
        f"   UUID: {msg['message_uuid']}"
    ]

    if include_content:
        content = msg.get('full_content', msg.get('summary', ''))
        if len(content) > 500:
            content = content[:497] + "..."
        lines.append(f"   Content: {content}")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Search Claude Code conversations')
    parser.add_argument('query', nargs='?', help='Search query (legacy keyword search)')
    parser.add_argument('--days', type=int, default=7,
                       help='Search last N days (default: 7)')
    parser.add_argument('--limit', type=int, default=20,
                       help='Maximum results (default: 20)')
    parser.add_argument('--project', help='Filter by project path')
    parser.add_argument('--context', metavar='UUID',
                       help='Get context for a specific message UUID')
    parser.add_argument('--depth', type=int, default=3,
                       help='Context depth (default: 3)')
    parser.add_argument('--tree', metavar='SESSION_ID',
                       help='Show full conversation tree')
    parser.add_argument('--list', action='store_true',
                       help='List recent conversations')
    parser.add_argument('--load', action='store_true',
                       help='Load recent context for Claude to read (NEW: context-first mode)')
    parser.add_argument('--full', metavar='UUID', nargs='+',
                       help='Fetch full content for message UUIDs')
    parser.add_argument('--summarize', metavar='N', type=int, nargs='?', const=-1,
                       help='Summarize unsummarized messages (optionally limit to N messages)')
    parser.add_argument('--inspect', metavar='N', type=int, nargs='?', const=10,
                       help='Inspect last N messages with metadata (default: 10)')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up: mark tool noise and remove summarizer conversations')
    parser.add_argument('--force', action='store_true',
                       help='Force re-summarization even if already summarized')
    parser.add_argument('--content', action='store_true',
                       help='Show full message content')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--db', default='~/.conversation-search/index.db',
                       help='Path to SQLite database')

    args = parser.parse_args()

    search = ConversationSearch(db_path=args.db)

    try:
        if args.cleanup:
            # Clean up database: mark tool noise and remove summarizer conversations
            from conversation_search.core.summarization import MessageSummarizer, is_summarizer_conversation

            print("🧹 Cleaning up database...")
            summarizer = MessageSummarizer(db_path=args.db)
            cursor = search.conn.cursor()

            # Step 1: Mark tool noise
            print("\n1️⃣ Marking tool noise messages...")
            cursor.execute("SELECT message_uuid, message_type, full_content as content FROM messages WHERE is_tool_noise = FALSE AND is_meta_conversation = FALSE")
            messages = [dict(row) for row in cursor.fetchall()]

            tool_noise_uuids = []
            for msg in messages:
                if summarizer.is_tool_noise(msg):
                    tool_noise_uuids.append(msg['message_uuid'])

            if tool_noise_uuids:
                summarizer.mark_tool_noise(tool_noise_uuids)
                print(f"   ✓ Marked {len(tool_noise_uuids)} messages as tool noise")
            else:
                print(f"   ✓ No new tool noise found")

            # Step 2: Find and remove summarizer conversations
            print("\n2️⃣ Finding summarizer conversations...")
            cursor.execute("""
                SELECT DISTINCT session_id, conversation_file
                FROM conversations
            """)
            conversations = [dict(row) for row in cursor.fetchall()]

            summarizer_sessions = []
            for conv in conversations:
                conv_file = Path(conv['conversation_file'])
                if not conv_file.exists():
                    continue

                # Read messages from this conversation
                try:
                    from indexer import ConversationIndexer
                    indexer = ConversationIndexer(db_path=args.db)
                    _, messages = indexer.parse_conversation_file(conv_file)

                    if is_summarizer_conversation(conv_file, messages):
                        summarizer_sessions.append(conv['session_id'])
                        print(f"   Found summarizer conversation: {conv_file.name}")
                except Exception as e:
                    continue

            if summarizer_sessions:
                # Delete summarizer conversations
                for session_id in summarizer_sessions:
                    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                    cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))

                search.conn.commit()
                print(f"   ✓ Removed {len(summarizer_sessions)} summarizer conversations")
            else:
                print(f"   ✓ No summarizer conversations found")

            # Step 3: Show stats
            print("\n📊 Final stats:")
            cursor.execute("SELECT COUNT(*) FROM messages")
            total_messages = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM messages WHERE is_tool_noise = TRUE")
            tool_noise_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM messages WHERE is_summarized = TRUE")
            summarized_count = cursor.fetchone()[0]

            print(f"   Total messages: {total_messages}")
            print(f"   Tool noise: {tool_noise_count} ({100*tool_noise_count/total_messages:.1f}%)")
            print(f"   Summarized: {summarized_count} ({100*summarized_count/total_messages:.1f}%)")
            print("\n✓ Cleanup complete!")

        elif args.inspect is not None:
            # Inspect messages with metadata
            cursor = search.conn.cursor()

            limit = args.inspect if args.inspect > 0 else 10

            sql = """
                SELECT
                    message_uuid,
                    message_type,
                    timestamp,
                    is_summarized,
                    is_tool_noise,
                    summary_method,
                    summary,
                    SUBSTR(full_content, 1, 100) as content_preview
                FROM messages
            """

            # Get the most recent N messages, then reverse for chronological display
            if args.days:
                cutoff = (datetime.now() - timedelta(days=args.days)).isoformat()
                sql += " WHERE timestamp >= ?"
                cursor.execute(sql + " ORDER BY timestamp DESC LIMIT ?", (cutoff, limit))
            else:
                cursor.execute(sql + " ORDER BY timestamp DESC LIMIT ?", (limit,))

            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()  # Oldest to newest for chronological display

            if not messages:
                print("No messages found")
                return

            # Print header
            print("\n" + "="*155)
            print(f"{'Time':<8} {'UUID':<10} {'Type':<4} {'Sum':<4} {'Noise':<5} {'Method':<8} {'Summary':<50} {'Content Preview':<40}")
            print("="*155)

            # Print messages
            for msg in messages:
                # Format timestamp
                time_str = format_timestamp(msg['timestamp'], include_date=False, include_seconds=True)
                uuid_short = msg['message_uuid'][:8]
                msg_type = "👤" if msg['message_type'] == 'user' else "🤖"
                is_sum = "✓" if msg['is_summarized'] else "✗"
                is_noise = "🔇" if msg['is_tool_noise'] else ""

                method = msg['summary_method'] or 'none'
                method_short = {
                    'ai_generated': 'ai',
                    'truncation': 'trunc',
                    'too_short': 'short',
                    'none': '-'
                }.get(method, method[:8])

                summary = (msg['summary'] or '')[:50]
                content = (msg['content_preview'] or '').replace('\n', ' ')[:40]

                print(f"{time_str:<8} {uuid_short:<10} {msg_type:<4} {is_sum:<4} {is_noise:<5} {method_short:<8} {summary:<50} {content:<40}")

            print("="*155)
            print(f"\nShowing {len(messages)} messages")

            # Stats
            summarized = sum(1 for m in messages if m['is_summarized'])
            ai_generated = sum(1 for m in messages if m['summary_method'] == 'ai_generated')
            tool_noise = sum(1 for m in messages if m['is_tool_noise'])

            print(f"Stats: {summarized}/{len(messages)} summarized | {ai_generated} AI-generated | {tool_noise} tool noise\n")

        elif args.summarize is not None:
            # Retroactive batch summarization
            summarizer = MessageSummarizer(db_path=args.db)

            print("🔍 Finding unsummarized messages...")

            # Query for unsummarized messages
            cursor = search.conn.cursor()

            if args.force:
                # Force re-summarization
                sql = """
                    SELECT message_uuid as uuid, message_type, full_content as content
                    FROM messages
                    WHERE 1=1
                """
            else:
                # Only unsummarized messages
                sql = """
                    SELECT message_uuid as uuid, message_type, full_content as content
                    FROM messages
                    WHERE is_summarized = FALSE AND is_tool_noise = FALSE AND is_meta_conversation = FALSE
                """

            if args.days:
                cutoff = (datetime.now() - timedelta(days=args.days)).isoformat()
                sql += " AND timestamp >= ?"
                cursor.execute(sql + " ORDER BY timestamp DESC", (cutoff,))
            else:
                cursor.execute(sql + " ORDER BY timestamp DESC")

            messages = [dict(row) for row in cursor.fetchall()]

            # Limit if specified
            if args.summarize > 0:
                messages = messages[:args.summarize]

            if not messages:
                print("✓ No messages need summarization")
                return

            print(f"Found {len(messages)} messages to summarize")

            # Filter by summarization needs
            needs_summary = []
            tool_noise_uuids = []
            too_short_uuids = []

            for msg in messages:
                should_summarize, reason = summarizer.needs_summarization(msg)

                if reason == 'tool_noise':
                    tool_noise_uuids.append(msg['uuid'])
                elif reason == 'too_short':
                    too_short_uuids.append(msg['uuid'])
                elif should_summarize or args.force:
                    needs_summary.append(msg)

            # Mark metadata
            if tool_noise_uuids:
                summarizer.mark_tool_noise(tool_noise_uuids)
                print(f"  Marked {len(tool_noise_uuids)} messages as tool noise")

            if too_short_uuids:
                summarizer.mark_too_short(too_short_uuids)
                print(f"  Marked {len(too_short_uuids)} messages as too short")

            # Batch summarize
            if needs_summary:
                print(f"\n📝 Batch summarizing {len(needs_summary)} messages...")
                batch_size = 20
                total_updated = 0

                for i in range(0, len(needs_summary), batch_size):
                    batch = needs_summary[i:i+batch_size]
                    batch_num = i//batch_size + 1
                    total_batches = (len(needs_summary)-1)//batch_size + 1

                    print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} messages)...")

                    summaries = summarizer.summarize_batch(batch)
                    if summaries:
                        updated = summarizer.update_database(summaries)
                        total_updated += updated
                        print(f"    ✓ Updated {updated} summaries")
                    else:
                        print(f"    ✗ No summaries generated")

                print(f"\n✓ Summarization complete! Updated {total_updated}/{len(needs_summary)} messages")
            else:
                print("✓ All messages already summarized")

        elif args.load:
            # NEW: Context-first mode
            context = search.load_context(
                days_back=args.days,
                project_path=args.project
            )
            print(context)

        elif args.full:
            # NEW: Fetch full content for specific UUIDs
            messages = search.get_full_messages(args.full)
            if args.json:
                print(json.dumps(messages, indent=2))
            else:
                for msg in messages:
                    time_str = format_timestamp(msg['timestamp'])
                    icon = "👤" if msg['message_type'] == 'user' else "🤖"
                    print(f"\n{icon} [{time_str}] {msg['project_path']}")
                    print(f"UUID: {msg['message_uuid']}")
                    print(f"Summary: {msg['summary']}\n")
                    print("--- Full Content ---")
                    content = msg['full_content']
                    if len(content) > 5000 and not args.content:
                        print(content[:5000] + f"\n\n... (truncated, {len(content)} chars total)")
                    else:
                        print(content)
                    print("-" * 50)

        elif args.list:
            results = search.list_recent_conversations(
                days_back=args.days,
                limit=args.limit,
                project_path=args.project
            )
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(f"\n📚 Recent conversations (last {args.days} days):\n")
                for conv in results:
                    time_str = format_timestamp(conv['last_message_at'])
                    print(f"[{time_str}] {conv['conversation_summary']}")
                    print(f"  {conv['message_count']} messages")
                    print(f"  {conv['project_path']}")
                    print(f"  Session: {conv['session_id']}")
                    print()

        elif args.context:
            context = search.get_conversation_context(
                args.context,
                depth=args.depth,
                include_children=True
            )
            if args.json:
                print(json.dumps(context, indent=2))
            else:
                if 'error' in context:
                    print(f"❌ {context['error']}")
                else:
                    print(f"\n📍 Context for message {args.context}\n")
                    print(f"Conversation: {context['conversation']['conversation_summary']}")
                    print(f"Project: {context['conversation']['project_path']}\n")

                    if context['ancestors']:
                        print(f"⬆️  Ancestors ({len(context['ancestors'])} levels up):\n")
                        for ancestor in context['ancestors']:
                            print(format_message_for_display(ancestor, args.content))
                            print()

                    print(f"🎯 Target Message:\n")
                    print(format_message_for_display(context['message'], args.content))
                    print()

                    if context['children']:
                        print(f"⬇️  Children ({len(context['children'])} branches):\n")
                        for child in context['children']:
                            print(format_message_for_display(child, args.content))
                            print()

        elif args.tree:
            tree_data = search.get_conversation_tree(args.tree)
            if args.json:
                print(json.dumps(tree_data, indent=2))
            else:
                if 'error' in tree_data:
                    print(f"❌ {tree_data['error']}")
                else:
                    print(f"\n🌳 Conversation Tree: {tree_data['conversation']['conversation_summary']}\n")
                    print(f"Project: {tree_data['conversation']['project_path']}")
                    print(f"Total messages: {tree_data['total_messages']}\n")
                    # TODO: Implement nice tree visualization

        elif args.query:
            results = search.search_conversations(
                query=args.query,
                days_back=args.days,
                limit=args.limit,
                project_path=args.project
            )

            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(f"\n🔍 Found {len(results)} matches for '{args.query}':\n")
                for msg in results:
                    print(format_message_for_display(msg, args.content))
                    print(f"   Conversation: {msg['conversation_summary']}")
                    print()

        else:
            parser.print_help()

    finally:
        search.close()


if __name__ == '__main__':
    main()
