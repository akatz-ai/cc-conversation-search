#!/usr/bin/env python3
"""Integration tests for date filtering in search and list"""

import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from conversation_search.core.search import ConversationSearch


class TestSearchWithDateFilters:
    """Test search_conversations with date parameters"""

    @pytest.fixture
    def db_with_data(self):
        """Create temporary database with test data"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Create schema
        conn.executescript("""
            CREATE TABLE messages (
                message_uuid TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_uuid TEXT,
                is_sidechain BOOLEAN DEFAULT FALSE,
                depth INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                message_type TEXT NOT NULL,
                project_path TEXT,
                conversation_file TEXT,
                summary TEXT,
                full_content TEXT NOT NULL,
                is_summarized BOOLEAN DEFAULT FALSE,
                is_tool_noise BOOLEAN DEFAULT FALSE,
                is_meta_conversation BOOLEAN DEFAULT FALSE,
                summary_method TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE conversations (
                session_id TEXT PRIMARY KEY,
                project_path TEXT,
                conversation_file TEXT,
                root_message_uuid TEXT,
                leaf_message_uuid TEXT,
                conversation_summary TEXT,
                first_message_at TEXT,
                last_message_at TEXT,
                message_count INTEGER DEFAULT 0,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE message_content_fts USING fts5(
                message_uuid UNINDEXED,
                full_content,
                content='messages',
                content_rowid='rowid'
            );
        """)

        # Insert test data spanning multiple days
        today = datetime.now().replace(hour=14, minute=30, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        week_ago = today - timedelta(days=7)

        test_messages = [
            ('msg-1', 'session-1', today, 'Testing Redis caching today'),
            ('msg-2', 'session-1', today, 'Added Redis configuration'),
            ('msg-3', 'session-2', yesterday, 'Fixed authentication bug yesterday'),
            ('msg-4', 'session-2', yesterday, 'Updated auth tests'),
            ('msg-5', 'session-3', two_days_ago, 'Implementing database migrations'),
            ('msg-6', 'session-4', week_ago, 'Started new feature development'),
        ]

        for msg_id, session_id, timestamp, content in test_messages:
            conn.execute("""
                INSERT INTO messages (
                    message_uuid, session_id, timestamp, message_type,
                    full_content, project_path, is_summarized
                )
                VALUES (?, ?, ?, 'user', ?, '/test/project', TRUE)
            """, (msg_id, session_id, timestamp.isoformat(), content))

            # Insert into FTS
            conn.execute("""
                INSERT INTO message_content_fts (message_uuid, full_content)
                VALUES (?, ?)
            """, (msg_id, content))

        # Insert conversations
        for session_id, last_time in [
            ('session-1', today),
            ('session-2', yesterday),
            ('session-3', two_days_ago),
            ('session-4', week_ago)
        ]:
            conn.execute("""
                INSERT INTO conversations (
                    session_id, project_path, conversation_summary,
                    first_message_at, last_message_at, message_count
                )
                VALUES (?, '/test/project', 'Test conversation', ?, ?, 1)
            """, (session_id, last_time.isoformat(), last_time.isoformat()))

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)
        Path(db_path + '-shm').unlink(missing_ok=True)
        Path(db_path + '-wal').unlink(missing_ok=True)

    def test_search_with_date_today(self, db_with_data):
        """Should find only today's messages"""
        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='Redis',
            date='today'
        )

        assert len(results) == 2
        assert all('msg-1' in r['message_uuid'] or 'msg-2' in r['message_uuid'] for r in results)
        search.close()

    def test_search_with_date_yesterday(self, db_with_data):
        """Should find only yesterday's messages"""
        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='auth',
            date='yesterday'
        )

        assert len(results) == 2
        assert all('msg-3' in r['message_uuid'] or 'msg-4' in r['message_uuid'] for r in results)
        search.close()

    def test_search_with_specific_date(self, db_with_data):
        """Should find messages from specific date"""
        two_days_ago = (datetime.now().date() - timedelta(days=2)).isoformat()

        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='database',
            date=two_days_ago
        )

        assert len(results) == 1
        assert results[0]['message_uuid'] == 'msg-5'
        search.close()

    def test_search_with_since_only(self, db_with_data):
        """Should find messages from since date onwards"""
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='',  # Match all
            since=yesterday,
            limit=10
        )

        # Should get today + yesterday (4 messages)
        assert len(results) >= 4
        search.close()

    def test_search_with_until_only(self, db_with_data):
        """Should find messages up to and including until date"""
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='',
            until=yesterday,
            limit=10
        )

        # Should not include today's messages
        assert all('msg-1' not in r['message_uuid'] and 'msg-2' not in r['message_uuid']
                   for r in results)
        search.close()

    def test_search_with_date_range(self, db_with_data):
        """Should find messages within date range"""
        two_days_ago = (datetime.now().date() - timedelta(days=2)).isoformat()
        today = datetime.now().date().isoformat()

        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='',
            since=two_days_ago,
            until=today,
            limit=10
        )

        # Should get messages from last 3 days (not week-old)
        assert any('msg-1' in r['message_uuid'] for r in results)  # today
        assert any('msg-5' in r['message_uuid'] for r in results)  # 2 days ago
        assert all('msg-6' not in r['message_uuid'] for r in results)  # week ago excluded
        search.close()

    def test_days_and_date_mutually_exclusive(self, db_with_data):
        """Should raise error when using --days with date filters"""
        search = ConversationSearch(db_path=db_with_data)

        with pytest.raises(ValueError, match="Cannot use --days with"):
            search.search_conversations(
                query='test',
                days_back=7,
                date='today'
            )

        with pytest.raises(ValueError, match="Cannot use --days with"):
            search.search_conversations(
                query='test',
                days_back=7,
                since='yesterday'
            )

        search.close()

    def test_backward_compatible_days_still_works(self, db_with_data):
        """Should still support --days parameter"""
        search = ConversationSearch(db_path=db_with_data)
        results = search.search_conversations(
            query='',
            days_back=2,  # Today + yesterday
            limit=10
        )

        # Should get at least 4 messages (2 from today, 2 from yesterday)
        assert len(results) >= 4
        search.close()


class TestListWithDateFilters:
    """Test list_recent_conversations with date parameters"""

    @pytest.fixture
    def db_with_conversations(self):
        """Create temporary database with test conversations"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        conn.executescript("""
            CREATE TABLE messages (
                message_uuid TEXT PRIMARY KEY,
                session_id TEXT,
                parent_uuid TEXT,
                is_sidechain BOOLEAN DEFAULT FALSE,
                depth INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                message_type TEXT NOT NULL,
                project_path TEXT,
                conversation_file TEXT,
                summary TEXT,
                full_content TEXT NOT NULL,
                is_summarized BOOLEAN DEFAULT FALSE,
                is_tool_noise BOOLEAN DEFAULT FALSE,
                is_meta_conversation BOOLEAN DEFAULT FALSE,
                summary_method TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE conversations (
                session_id TEXT PRIMARY KEY,
                project_path TEXT,
                conversation_file TEXT,
                root_message_uuid TEXT,
                leaf_message_uuid TEXT,
                conversation_summary TEXT,
                first_message_at TEXT,
                last_message_at TEXT,
                message_count INTEGER DEFAULT 0,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        today = datetime.now().replace(hour=14, minute=30, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        conversations = [
            ('session-today', 'Redis work', today),
            ('session-yesterday', 'Auth fixes', yesterday),
            ('session-week', 'Old feature', week_ago),
        ]

        for session_id, summary, timestamp in conversations:
            conn.execute("""
                INSERT INTO conversations (
                    session_id, conversation_summary, project_path,
                    first_message_at, last_message_at, message_count
                )
                VALUES (?, ?, '/test/project', ?, ?, 5)
            """, (session_id, summary, timestamp.isoformat(), timestamp.isoformat()))

        conn.commit()
        conn.close()

        yield db_path

        Path(db_path).unlink(missing_ok=True)
        Path(db_path + '-shm').unlink(missing_ok=True)
        Path(db_path + '-wal').unlink(missing_ok=True)

    def test_list_with_date_today(self, db_with_conversations):
        """Should list only today's conversations"""
        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(date='today')

        assert len(convs) == 1
        assert convs[0]['session_id'] == 'session-today'
        search.close()

    def test_list_with_date_yesterday(self, db_with_conversations):
        """Should list only yesterday's conversations"""
        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(date='yesterday')

        assert len(convs) == 1
        assert convs[0]['session_id'] == 'session-yesterday'
        search.close()

    def test_list_with_since_yesterday(self, db_with_conversations):
        """Should list conversations from yesterday onwards"""
        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(since='yesterday')

        assert len(convs) == 2
        session_ids = {c['session_id'] for c in convs}
        assert 'session-today' in session_ids
        assert 'session-yesterday' in session_ids
        search.close()

    def test_list_with_date_range(self, db_with_conversations):
        """Should list conversations within date range"""
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
        today = datetime.now().date().isoformat()

        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(since=yesterday, until=today)

        assert len(convs) == 2
        search.close()

    def test_list_days_still_works(self, db_with_conversations):
        """Should still support days_back parameter"""
        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(days_back=2)

        # Should get today + yesterday
        assert len(convs) >= 2
        search.close()

    def test_list_days_none_with_date(self, db_with_conversations):
        """Should allow days_back=None with date filters"""
        search = ConversationSearch(db_path=db_with_conversations)
        convs = search.list_recent_conversations(days_back=None, date='today')

        assert len(convs) == 1
        search.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
