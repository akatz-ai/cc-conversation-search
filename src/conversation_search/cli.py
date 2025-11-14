#!/usr/bin/env python3
"""Unified CLI for conversation-search"""

import argparse
import json
import sys
from pathlib import Path

from conversation_search.core.indexer import ConversationIndexer
from conversation_search.core.search import ConversationSearch


def cmd_init(args):
    """Initialize the database and run initial indexing"""
    print("Conversation Search - Initializing")
    print("=" * 50)

    db_path = Path.home() / ".conversation-search" / "index.db"

    if db_path.exists() and not args.force:
        print(f"✓ Database already exists: {db_path}")
        print("  Use --force to reinitialize")
        return

    # Create indexer (initializes DB)
    print(f"Creating database: {db_path}")
    indexer = ConversationIndexer(db_path=str(db_path))

    # Index recent conversations
    days = args.days
    print(f"\nIndexing conversations from last {days} days...")
    files = indexer.scan_conversations(days_back=days)

    if not files:
        print("  No conversations found")
        indexer.close()
        return

    print(f"  Found {len(files)} conversation files")

    for i, conv_file in enumerate(files, 1):
        try:
            print(f"  [{i}/{len(files)}] {conv_file.name}", end="\r")
            indexer.index_conversation(conv_file, summarize=not args.no_extract)
        except Exception as e:
            print(f"\n  Error indexing {conv_file.name}: {e}")

    print(f"\n\n✓ Initialization complete!")
    print(f"  Database: {db_path}")
    print(f"\nNext steps:")
    print(f"  • Search conversations: conversation-search search '<query>'")
    print(f"  • List recent: conversation-search list")
    print(f"  • Re-index: conversation-search index")

    indexer.close()


def cmd_index(args):
    """Index conversations (JIT - fast without AI calls)"""
    indexer = ConversationIndexer()

    files = indexer.scan_conversations(days_back=args.days if not args.all else None)

    if not files:
        print("No conversations to index")
        return

    print(f"Indexing {len(files)} conversations...")

    for i, conv_file in enumerate(files, 1):
        try:
            print(f"[{i}/{len(files)}] {conv_file.name}", end="\r")
            indexer.index_conversation(conv_file, summarize=not args.no_extract)
        except Exception as e:
            print(f"\nError indexing {conv_file.name}: {e}")

    print(f"\n✓ Indexed {len(files)} conversations")
    indexer.close()


def cmd_search(args):
    """Search conversations"""
    search = ConversationSearch()

    try:
        results = search.search_conversations(
            query=args.query,
            days_back=args.days,
            limit=args.limit,
            project_path=args.project
        )
    except Exception as e:
        print(f"Error: {e}")
        raise

    if args.json:
        print(json.dumps([dict(r) for r in results], indent=2))
        return

    if not results:
        print(f"No results found for: {args.query}")
        return

    print(f"🔍 Found {len(results)} matches for '{args.query}':\n")

    for result in results:
        icon = "👤" if result['message_type'] == 'user' else "🤖"
        timestamp = result['timestamp'][:16].replace('T', ' ')

        # Convert project_path hash to actual path
        project_dir = result['project_path'].replace('-', '/')
        if not project_dir.startswith('/'):
            project_dir = f"/{project_dir}"

        print(f"{icon}  {result['conversation_summary']}")
        print(f"   Session: {result['session_id']}")
        print(f"   Project: {project_dir}")
        print(f"   Time: {timestamp}")
        print(f"   Message: {result['message_uuid']}")

        if args.content:
            content = search.get_full_message_content(result['message_uuid'])
            if content:
                print(f"\n   {content[:300]}...")
        else:
            print(f"\n   {result['summary']}")

        print(f"\n   Resume:")
        print(f"     cd {project_dir}")
        print(f"     clauded --resume {result['session_id']}")
        print()


def cmd_context(args):
    """Get context around a message"""
    search = ConversationSearch()

    result = search.get_conversation_context(
        message_uuid=args.uuid,
        depth=args.depth
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Context for message: {args.uuid}\n")

    if 'error' in result:
        print(f"Error: {result['error']}")
        return

    # Show parents
    if result.get('ancestors'):
        print("📜 Parent messages:")
        for msg in result['ancestors']:
            icon = "👤" if msg.get('message_type') == 'user' else "🤖"
            print(f"  {icon} {msg.get('summary', 'No summary')}")
        print()

    # Show target message
    if result.get('message'):
        print("🎯 Target message:")
        msg = result['message']
        icon = "👤" if msg.get('message_type') == 'user' else "🤖"
        if args.content and msg.get('full_content'):
            print(f"  {icon} {msg['full_content']}")
        else:
            print(f"  {icon} {msg.get('summary', 'No summary')}")
        print()

    # Show children
    if result.get('children'):
        print("💬 Responses:")
        for msg in result['children']:
            icon = "👤" if msg.get('message_type') == 'user' else "🤖"
            print(f"  {icon} {msg.get('summary', 'No summary')}")


def cmd_list(args):
    """List recent conversations"""
    search = ConversationSearch()

    convs = search.list_recent_conversations(days_back=args.days, limit=args.limit)

    if args.json:
        print(json.dumps([dict(c) for c in convs], indent=2))
        return

    if not convs:
        print("No conversations found")
        return

    print(f"Recent conversations (last {args.days} days):\n")

    for conv in convs:
        timestamp = conv['last_message_at'][:16].replace('T', ' ')
        print(f"[{timestamp}] {conv['conversation_summary']}")
        print(f"  {conv['message_count']} messages")
        print(f"  {conv['project_path']}")
        print(f"  Session: {conv['session_id']}")
        print()


def cmd_tree(args):
    """Show conversation tree"""
    search = ConversationSearch()

    tree = search.get_conversation_tree(args.session_id)

    if args.json:
        print(json.dumps(tree, indent=2))
        return

    print(f"Conversation tree: {args.session_id}\n")

    if 'error' in tree:
        print(f"Error: {tree['error']}")
        return

    # Simple tree visualization
    def print_tree(nodes, indent=0):
        for node in nodes:
            icon = "👤" if node['message_type'] == 'user' else "🤖"
            prefix = "  " * indent
            summary = node['summary'][:80]
            print(f"{prefix}{icon} {summary}")
            if node.get('children'):
                print_tree(node['children'], indent + 1)

    print_tree(tree['tree'])


def cmd_resume(args):
    """Get session resumption commands for a message UUID"""
    search = ConversationSearch()

    # Get message info
    cursor = search.conn.cursor()
    cursor.execute("""
        SELECT m.session_id, m.project_path, m.timestamp, m.summary
        FROM messages m
        WHERE m.message_uuid = ?
    """, (args.uuid,))

    result = cursor.fetchone()

    if not result:
        print(f"Message not found: {args.uuid}")
        sys.exit(1)

    session_id = result['session_id']
    project_path = result['project_path']

    # Convert project_path hash back to actual path
    project_dir = project_path.replace('-', '/')
    if not project_dir.startswith('/'):
        project_dir = f"/{project_dir}"

    print(f"cd {project_dir}")
    print(f"clauded --resume {session_id}")


def main():
    parser = argparse.ArgumentParser(
        prog='conversation-search',
        description='Find and resume Claude Code conversations using semantic search'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # init command
    init_parser = subparsers.add_parser('init', help='Initialize database and index')
    init_parser.add_argument('--days', type=int, default=7, help='Days of history to index (default: 7)')
    init_parser.add_argument('--no-extract', action='store_true', help='Skip smart extraction (store only raw content)')
    init_parser.add_argument('--force', action='store_true', help='Reinitialize existing database')
    init_parser.set_defaults(func=cmd_init)

    # index command
    index_parser = subparsers.add_parser('index', help='Index conversations (JIT - runs before search)')
    index_parser.add_argument('--days', type=int, default=1, help='Days back to index (default: 1)')
    index_parser.add_argument('--all', action='store_true', help='Index all conversations')
    index_parser.add_argument('--no-extract', action='store_true', help='Skip smart extraction')
    index_parser.set_defaults(func=cmd_index)

    # search command
    search_parser = subparsers.add_parser('search', help='Search conversations')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--days', type=int, help='Limit to last N days')
    search_parser.add_argument('--project', help='Filter by project path')
    search_parser.add_argument('--limit', type=int, default=20, help='Max results (default: 20)')
    search_parser.add_argument('--content', action='store_true', help='Show full content')
    search_parser.add_argument('--json', action='store_true', help='Output as JSON')
    search_parser.set_defaults(func=cmd_search)

    # context command
    context_parser = subparsers.add_parser('context', help='Get context around a message')
    context_parser.add_argument('uuid', help='Message UUID')
    context_parser.add_argument('--depth', type=int, default=3, help='Parent depth (default: 3)')
    context_parser.add_argument('--content', action='store_true', help='Show full content')
    context_parser.add_argument('--json', action='store_true', help='Output as JSON')
    context_parser.set_defaults(func=cmd_context)

    # list command
    list_parser = subparsers.add_parser('list', help='List recent conversations')
    list_parser.add_argument('--days', type=int, default=7, help='Days back (default: 7)')
    list_parser.add_argument('--limit', type=int, default=20, help='Max results (default: 20)')
    list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    list_parser.set_defaults(func=cmd_list)

    # tree command
    tree_parser = subparsers.add_parser('tree', help='Show conversation tree')
    tree_parser.add_argument('session_id', help='Session ID')
    tree_parser.add_argument('--json', action='store_true', help='Output as JSON')
    tree_parser.set_defaults(func=cmd_tree)

    # resume command
    resume_parser = subparsers.add_parser('resume', help='Get session resumption commands')
    resume_parser.add_argument('uuid', help='Message UUID')
    resume_parser.set_defaults(func=cmd_resume)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nRun 'conversation-search init' to initialize the database")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
