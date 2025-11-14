#!/usr/bin/env python3
"""
Tests for conversation-search pair detection and filtering.

These tests verify that we correctly identify and skip user-Claude message pairs
where Claude uses the conversation-search tool, preventing meta-conversation pollution.
"""

import pytest
from typing import List, Dict, Set

# Import functions we'll implement
from conversation_search.core.summarization import message_uses_conversation_search
from conversation_search.core.indexer import ConversationIndexer


class TestMessageUsesConversationSearch:
    """Test detection of messages that use the conversation-search tool."""

    def test_detects_bash_tool_with_cc_conversation_search(self):
        """Should detect when Claude runs cc-conversation-search via Bash."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': '[Tool: Bash]\ncc-conversation-search search "redis" --days 7 --json\n...'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_skill_loading_marker(self):
        """Should detect skill activation markers."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'Let me search for that.\n\nThe "conversation-search" skill is loading\n⎿  Allowed 1 tools for this command'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_skill_is_running(self):
        """Should detect alternative skill markers."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'conversation-search skill is running...\nSearching for your query...'
        }
        assert message_uses_conversation_search(message) is True

    def test_ignores_discussion_about_tool(self):
        """Should NOT detect when Claude is just discussing the tool."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'You can use the cc-conversation-search tool to find past conversations. Here is how it works...'
        }
        assert message_uses_conversation_search(message) is False

    def test_ignores_user_messages(self):
        """Should never flag user messages (even if they mention the tool)."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'user',
            'content': 'Run cc-conversation-search for me'
        }
        assert message_uses_conversation_search(message) is False

    def test_ignores_normal_assistant_messages(self):
        """Should not flag normal Claude responses."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'Let me help you implement that feature. [Tool: Read] [Tool: Edit] ...'
        }
        assert message_uses_conversation_search(message) is False

    def test_case_insensitive_skill_detection(self):
        """Skill markers should be case-insensitive."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'The "Conversation-Search" SKILL IS LOADING'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_flags_before_subcommand(self):
        """Should detect cc-conversation-search with flags before subcommand."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': '[Tool: Bash]\ncc-conversation-search --json search "foo"\n...'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_help_flag(self):
        """Should detect cc-conversation-search --help."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': '[Tool: Bash]\ncc-conversation-search --help\n...'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_version_flag(self):
        """Should detect cc-conversation-search --version."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'cc-conversation-search -v'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_uv_tool_upgrade(self):
        """Should detect uv tool upgrade cc-conversation-search."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': '[Tool: Bash]\nuv tool upgrade cc-conversation-search\n...'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_pip_upgrade(self):
        """Should detect pip install --upgrade cc-conversation-search."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'pip install --upgrade cc-conversation-search'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_command_existence_check(self):
        """Should detect command -v cc-conversation-search."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'if command -v cc-conversation-search &> /dev/null; then\n    echo "found"\nfi'
        }
        assert message_uses_conversation_search(message) is True

    def test_detects_which_command(self):
        """Should detect which cc-conversation-search."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'which cc-conversation-search'
        }
        assert message_uses_conversation_search(message) is True

    def test_skill_activation_with_specific_verbs(self):
        """Should detect quoted skill name with activation verbs."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'The "conversation-search" skill is now activated and running'
        }
        assert message_uses_conversation_search(message) is True

    def test_ignores_skill_discussion_without_activation(self):
        """Should NOT detect when discussing skill without activation verbs."""
        message = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'The "conversation-search" skill can help you find conversations'
        }
        assert message_uses_conversation_search(message) is False

    def test_proximity_check_for_allowed_tools(self):
        """Should check proximity of conversation-search to allowed tools marker."""
        # Should detect when close together
        message_close = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'Allowed 1 tools for this command\nconversation-search'
        }
        assert message_uses_conversation_search(message_close) is True

        # Should NOT detect when far apart (>100 chars)
        message_far = {
            'uuid': 'test-uuid',
            'message_type': 'assistant',
            'content': 'Allowed 1 tools for this command\n' + ('x' * 150) + 'conversation-search'
        }
        assert message_uses_conversation_search(message_far) is False


class TestMarkMetaConversations:
    """Test marking user-Claude pairs where Claude used conversation-search."""

    def test_marks_simple_pair(self):
        """Should mark a simple user request + Claude search response pair."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Find that Redis conversation'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': '[Tool: Bash]\ncc-conversation-search search "redis"\nFound it in session xyz'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        assert meta_uuids == {'msg-a', 'msg-b'}
        assert messages[0].get('is_meta_conversation') is True
        assert messages[1].get('is_meta_conversation') is True

    def test_preserves_work_after_search(self):
        """Should only mark the search pair, not subsequent work."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Find Redis conversation'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "redis"\nFound it!'
            },
            {
                'uuid': 'msg-c',
                'parent_uuid': 'msg-b',
                'message_type': 'user',
                'content': 'Great! Now help me implement Redis caching'
            },
            {
                'uuid': 'msg-d',
                'parent_uuid': 'msg-c',
                'message_type': 'assistant',
                'content': 'Let me help with Redis caching...'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        # Only mark the search pair
        assert meta_uuids == {'msg-a', 'msg-b'}
        assert messages[0].get('is_meta_conversation') is True
        assert messages[1].get('is_meta_conversation') is True
        # These should NOT be marked
        assert 'msg-c' not in meta_uuids
        assert 'msg-d' not in meta_uuids
        assert messages[2].get('is_meta_conversation') is not True
        assert messages[3].get('is_meta_conversation') is not True

    def test_handles_multiple_search_pairs(self):
        """Should find multiple search pairs in one conversation."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Find Redis conversation'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "redis"\nFound 3 results'
            },
            {
                'uuid': 'msg-c',
                'parent_uuid': 'msg-b',
                'message_type': 'user',
                'content': 'The one from last week'
            },
            {
                'uuid': 'msg-d',
                'parent_uuid': 'msg-c',
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "redis last week"\nHere it is!'
            },
            {
                'uuid': 'msg-e',
                'parent_uuid': 'msg-d',
                'message_type': 'user',
                'content': 'Perfect, help me implement it'
            },
            {
                'uuid': 'msg-f',
                'parent_uuid': 'msg-e',
                'message_type': 'assistant',
                'content': 'Let me help you implement...'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        # Should skip both pairs
        assert meta_uuids == {'msg-a', 'msg-b', 'msg-c', 'msg-d'}
        # Real work preserved
        assert 'msg-e' not in meta_uuids
        assert 'msg-f' not in meta_uuids

    def test_handles_branching_sidechain(self):
        """Should handle conversation branches (sidechains) correctly."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Help with auth',
                'is_sidechain': False
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'Sure, I can help',
                'is_sidechain': False
            },
            {
                'uuid': 'msg-c',
                'parent_uuid': 'msg-b',
                'message_type': 'user',
                'content': 'Find that auth conversation',
                'is_sidechain': True
            },
            {
                'uuid': 'msg-d',
                'parent_uuid': 'msg-c',
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "auth"\nFound it',
                'is_sidechain': True
            },
            {
                'uuid': 'msg-e',
                'parent_uuid': 'msg-b',
                'message_type': 'user',
                'content': 'Continue with original plan',
                'is_sidechain': False
            },
            {
                'uuid': 'msg-f',
                'parent_uuid': 'msg-e',
                'message_type': 'assistant',
                'content': 'Let me continue...',
                'is_sidechain': False
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        # Only skip the sidechain search pair
        assert meta_uuids == {'msg-c', 'msg-d'}
        # Main chain preserved
        assert 'msg-a' not in meta_uuids
        assert 'msg-b' not in meta_uuids
        assert 'msg-e' not in meta_uuids
        assert 'msg-f' not in meta_uuids

    def test_empty_messages_list(self):
        """Should handle empty message list gracefully."""
        messages = []

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        assert meta_uuids == set()

    def test_no_search_messages(self):
        """Should return empty set when no search tool usage found."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Help me implement Redis caching'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'Let me help with that. [Tool: Read] [Tool: Edit]'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        assert meta_uuids == set()

    def test_orphaned_search_response(self):
        """Should handle search response with no parent gracefully."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,  # Root message
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "redis"\nFound it!'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        # Should still mark the search response even without parent
        assert 'msg-a' in meta_uuids

    def test_search_response_with_assistant_parent(self):
        """Should not add parent if parent is not a user message."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'assistant',
                'content': 'Let me check something...'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'cc-conversation-search search "redis"\nFound it!'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        # Should skip search response but not assistant parent
        assert meta_uuids == {'msg-b'}
        assert 'msg-a' not in meta_uuids

    def test_skill_activation_markers(self):
        """Should detect pairs using skill activation markers."""
        messages = [
            {
                'uuid': 'msg-a',
                'parent_uuid': None,
                'message_type': 'user',
                'content': 'Find conversations about git merge'
            },
            {
                'uuid': 'msg-b',
                'parent_uuid': 'msg-a',
                'message_type': 'assistant',
                'content': 'Let me search for that.\n\nThe "conversation-search" skill is loading\n⎿  Allowed 1 tools for this command'
            },
        ]

        indexer = ConversationIndexer(db_path=":memory:")
        meta_uuids = indexer._mark_meta_conversations(messages)

        assert meta_uuids == {'msg-a', 'msg-b'}


class TestIntegrationWithIndexer:
    """Test integration of pair detection with the indexer."""

    def test_filters_messages_during_indexing(self):
        """Should filter out search pairs before inserting into database."""
        # This will be an integration test once we implement the filtering
        # For now, we're just defining the expected behavior
        pass

    def test_logs_skipped_pairs(self):
        """Should log how many pairs were skipped."""
        # Test that appropriate logging happens
        pass

    def test_recalculates_depths_after_filtering(self):
        """Should recalculate message depths after filtering."""
        # Ensure depth calculation works correctly with filtered messages
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
