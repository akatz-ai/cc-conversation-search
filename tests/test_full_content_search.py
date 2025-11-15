#!/usr/bin/env python3
"""Tests for full-content FTS search with snippet extraction"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
from conversation_search.core.indexer import ConversationIndexer
from conversation_search.core.search import ConversationSearch


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)
    # Clean up WAL files
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)


@pytest.fixture
def indexer(temp_db):
    """Create an indexer with temp database"""
    return ConversationIndexer(db_path=temp_db, quiet=True)


@pytest.fixture
def search_engine(temp_db):
    """Create a search engine with temp database"""
    return ConversationSearch(db_path=temp_db)


class TestFullContentFTSIndexing:
    """Test that full content is indexed in FTS"""

    def test_fts_table_exists(self, indexer):
        """Should create message_content_fts table"""
        cursor = indexer.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='message_content_fts'
        """)
        assert cursor.fetchone() is not None

    def test_full_content_indexed(self, indexer):
        """Should index full_content field in FTS, not summary"""
        # Insert a test message
        cursor = indexer.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test-uuid-1',
            'session-1',
            datetime.now().isoformat(),
            'assistant',
            'This is a long message with unique phrase FINDME in the middle of content',
            False
        ))
        indexer.conn.commit()

        # Verify FTS can find it
        cursor.execute("""
            SELECT message_uuid FROM message_content_fts
            WHERE full_content MATCH 'FINDME'
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 'test-uuid-1'

    def test_phrase_in_middle_of_long_message(self, indexer):
        """Should find phrases even in middle of very long messages"""
        # Create a long message with phrase at position ~5000
        prefix = "A" * 5000
        suffix = "Z" * 5000
        content = f"{prefix} absolutely right in the middle {suffix}"

        cursor = indexer.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test-uuid-long',
            'session-1',
            datetime.now().isoformat(),
            'assistant',
            content,
            False
        ))
        indexer.conn.commit()

        # Should find it via FTS
        cursor.execute("""
            SELECT message_uuid FROM message_content_fts
            WHERE full_content MATCH 'absolutely AND right'
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 'test-uuid-long'


class TestSnippetExtraction:
    """Test snippet extraction with context around matches"""

    def test_snippet_function_returns_context(self, indexer):
        """Should return text around the matched phrase"""
        cursor = indexer.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test-uuid-snippet',
            'session-1',
            datetime.now().isoformat(),
            'assistant',
            'This is some context before the TARGETPHRASE and some context after it.',
            False
        ))
        indexer.conn.commit()

        # Extract snippet
        cursor.execute("""
            SELECT snippet(message_content_fts, 1, '**', '**', '...', 64)
            FROM message_content_fts
            WHERE full_content MATCH 'TARGETPHRASE'
        """)
        snippet = cursor.fetchone()[0]

        # Should contain the matched phrase with markers
        assert '**TARGETPHRASE**' in snippet
        # Should contain context words
        assert 'before' in snippet
        assert 'after' in snippet

    def test_snippet_token_limits(self, indexer):
        """Should respect token limit parameter"""
        long_text = "word " * 200  # 200 words
        long_text += "MATCH "
        long_text += "word " * 200

        cursor = indexer.conn.cursor()
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test-uuid-long-snippet',
            'session-1',
            datetime.now().isoformat(),
            'assistant',
            long_text,
            False
        ))
        indexer.conn.commit()

        # Get snippets with different token limits
        cursor.execute("""
            SELECT
                snippet(message_content_fts, 1, '', '', '', 10) as short,
                snippet(message_content_fts, 1, '', '', '', 64) as medium,
                snippet(message_content_fts, 1, '', '', '', 200) as long
            FROM message_content_fts
            WHERE full_content MATCH 'MATCH'
        """)
        short, medium, long = cursor.fetchone()

        # Longer token limits should produce longer snippets
        assert len(short) < len(medium) < len(long)
        # All should contain the match
        assert 'MATCH' in short
        assert 'MATCH' in medium
        assert 'MATCH' in long


class TestSearchWithSnippets:
    """Test the search_conversations method with snippet results"""

    def setup_test_messages(self, indexer):
        """Insert test messages with various content patterns"""
        messages = [
            {
                'uuid': 'msg-1',
                'session': 'session-1',
                'content': 'You are absolutely right about the authentication bug fix.',
                'type': 'assistant'
            },
            {
                'uuid': 'msg-2',
                'session': 'session-2',
                'content': 'The user asked a question and I responded with detailed info about authentication.',
                'type': 'assistant'
            },
            {
                'uuid': 'msg-3',
                'session': 'session-3',
                'content': ('This is some initial context. ' * 50) + ' You are absolutely right about this middle part. ' + ('This is trailing context. ' * 50),
                'type': 'assistant'
            },
        ]

        cursor = indexer.conn.cursor()
        for msg in messages:
            cursor.execute("""
                INSERT INTO messages (
                    message_uuid, session_id, timestamp, message_type,
                    full_content, is_meta_conversation
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                msg['uuid'],
                msg['session'],
                datetime.now().isoformat(),
                msg['type'],
                msg['content'],
                False
            ))

            # Insert conversation metadata
            cursor.execute("""
                INSERT OR IGNORE INTO conversations (
                    session_id, project_path, conversation_file,
                    first_message_at, last_message_at, message_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                msg['session'],
                '/test/project',
                '/test/file.jsonl',
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                1
            ))

        indexer.conn.commit()

    def test_search_returns_snippets_not_summaries(self, indexer, search_engine):
        """Should return context snippets in results"""
        self.setup_test_messages(indexer)

        results = search_engine.search_conversations('absolutely right')

        assert len(results) == 2  # msg-1 and msg-3

        # Results should have context_snippet field
        for result in results:
            assert 'context_snippet' in result
            # Snippet should have match markers from FTS
            assert '**' in result['context_snippet'] or 'absolutely right' in result['context_snippet'].lower()

    def test_search_snippet_shows_context(self, indexer, search_engine):
        """Snippets should show text around the match"""
        self.setup_test_messages(indexer)

        results = search_engine.search_conversations('absolutely right')

        # Find the first message result
        msg1_result = next(r for r in results if r['message_uuid'] == 'msg-1')
        snippet = msg1_result['context_snippet']

        # Should contain context words from original message
        assert 'authentication' in snippet.lower()
        assert 'bug' in snippet.lower()

    def test_search_with_configurable_snippet_size(self, indexer, search_engine):
        """Should allow configuring snippet token size"""
        self.setup_test_messages(indexer)

        # Search with small snippet
        results_small = search_engine.search_conversations(
            'absolutely right',
            snippet_tokens=10
        )

        # Search with large snippet
        results_large = search_engine.search_conversations(
            'absolutely right',
            snippet_tokens=200
        )

        # Same number of results
        assert len(results_small) == len(results_large)

        # But different snippet sizes
        small_snippet = results_small[0]['context_snippet']
        large_snippet = results_large[0]['context_snippet']
        assert len(small_snippet) < len(large_snippet)


class TestMetaConversationFiltering:
    """Test that meta-conversations are still filtered"""

    def test_meta_conversations_excluded_from_search(self, indexer, search_engine):
        """Should not return messages marked as meta-conversations"""
        cursor = indexer.conn.cursor()

        # Create conversations first
        for session_id in ['session-meta', 'session-normal']:
            cursor.execute("""
                INSERT INTO conversations (
                    session_id, project_path, conversation_file,
                    first_message_at, last_message_at, message_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                '/test/project',
                '/test/file.jsonl',
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                1
            ))

        # Insert meta-conversation message
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'meta-msg',
            'session-meta',
            datetime.now().isoformat(),
            'assistant',
            'Running conversation search tool to find historical messages',
            True  # This is a meta-conversation
        ))

        # Insert normal message with same content
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'normal-msg',
            'session-normal',
            datetime.now().isoformat(),
            'assistant',
            'Running conversation search tool to find historical messages',
            False  # Normal conversation
        ))

        indexer.conn.commit()

        # Search should only return normal message
        results = search_engine.search_conversations('conversation search tool')

        assert len(results) == 1
        assert results[0]['message_uuid'] == 'normal-msg'


class TestDateFilteringWithFullContent:
    """Test that date filtering still works with full-content search"""

    def test_date_filter_on_message_timestamps(self, indexer, search_engine):
        """Should filter by message timestamp, not file mtime"""
        cursor = indexer.conn.cursor()

        # Create conversations first
        for session_id in ['session-old', 'session-recent']:
            cursor.execute("""
                INSERT INTO conversations (
                    session_id, project_path, conversation_file,
                    first_message_at, last_message_at, message_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                '/test/project',
                '/test/file.jsonl',
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                1
            ))

        # Insert old message
        old_time = datetime(2025, 10, 1, 12, 0, 0)
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'old-msg',
            'session-old',
            old_time.isoformat() + 'Z',
            'assistant',
            'This is old content with KEYWORD',
            False
        ))

        # Insert recent message
        recent_time = datetime(2025, 11, 14, 12, 0, 0)
        cursor.execute("""
            INSERT INTO messages (
                message_uuid, session_id, timestamp, message_type,
                full_content, is_meta_conversation
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'recent-msg',
            'session-recent',
            recent_time.isoformat() + 'Z',
            'assistant',
            'This is recent content with KEYWORD',
            False
        ))

        indexer.conn.commit()

        # Search with date filter (last 7 days from Nov 14)
        results = search_engine.search_conversations(
            'KEYWORD',
            days_back=7
        )

        # Should only find recent message
        assert len(results) == 1
        assert results[0]['message_uuid'] == 'recent-msg'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
