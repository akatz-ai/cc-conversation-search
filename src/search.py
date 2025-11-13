#!/usr/bin/env python3
"""
Claude Finder Search Tools
Provides search and retrieval tools for Claude to query conversation history
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta


class ConversationSearch:
    def __init__(self, db_path: str = "~/.claude-finder/index.db"):
        self.db_path = Path(db_path).expanduser()
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found at {self.db_path}. "
                "Run the indexer first: python src/indexer.py"
            )
        self.conn = sqlite3.connect(str(self.db_path), timeout=10.0)

        # Enable WAL mode for concurrent access
        self.conn.execute("PRAGMA journal_mode=WAL")

        self.conn.row_factory = sqlite3.Row

    def search_conversations(
        self,
        query: str,
        days_back: Optional[int] = None,
        limit: int = 20,
        project_path: Optional[str] = None
    ) -> List[Dict]:
        """
        Search conversations using full-text search on summaries

        Args:
            query: Search query
            days_back: Limit to last N days (None = all time)
            limit: Maximum number of results
            project_path: Filter by project path

        Returns:
            List of matching messages with context
        """
        cursor = self.conn.cursor()

        # Sanitize query for FTS5 - escape special characters
        # FTS5 uses: AND OR NOT " * ( )
        # For simple searches, just quote the whole thing
        fts_query = query
        if not any(op in query for op in [' AND ', ' OR ', ' NOT ', '"']):
            # Simple query - make it a phrase or use wildcards
            terms = query.split()
            if len(terms) == 1:
                # Single word - use prefix matching
                fts_query = f'{terms[0]}*'
            else:
                # Multiple words - search for all terms (implicit AND)
                fts_query = ' '.join(f'{term}*' for term in terms)

        # Build query
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
                m.summary,
                c.conversation_summary,
                c.conversation_file
            FROM messages m
            JOIN conversations c ON m.session_id = c.session_id
            WHERE m.message_uuid IN (
                SELECT message_uuid FROM message_summaries_fts
                WHERE summary MATCH ?
            )
        """

        params = [fts_query]

        if days_back:
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            sql += " AND m.timestamp >= ?"
            params.append(cutoff)

        if project_path:
            sql += " AND m.project_path = ?"
            params.append(project_path)

        sql += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        results = cursor.fetchall()

        return [dict(row) for row in results]

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
        days_back: int = 7,
        limit: int = 20,
        project_path: Optional[str] = None
    ) -> List[Dict]:
        """
        List recent conversations

        Returns:
            List of conversation metadata
        """
        cursor = self.conn.cursor()

        sql = """
            SELECT * FROM conversations
            WHERE 1=1
        """
        params = []

        if days_back:
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

    def close(self):
        """Close database connection"""
        self.conn.close()


def format_message_for_display(msg: Dict, include_content: bool = False) -> str:
    """Format a message for human-readable display"""
    timestamp = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
    time_str = timestamp.strftime('%Y-%m-%d %H:%M')

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
    parser.add_argument('query', nargs='?', help='Search query')
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
    parser.add_argument('--content', action='store_true',
                       help='Show full message content')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--db', default='~/.claude-finder/index.db',
                       help='Path to SQLite database')

    args = parser.parse_args()

    search = ConversationSearch(db_path=args.db)

    try:
        if args.list:
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
                    timestamp = datetime.fromisoformat(conv['last_message_at'].replace('Z', '+00:00'))
                    time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                    print(f"[{time_str}] {conv['conversation_summary']}")
                    print(f"   Project: {conv['project_path']}")
                    print(f"   Messages: {conv['message_count']}")
                    print(f"   Session: {conv['session_id']}")
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
