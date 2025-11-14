#!/usr/bin/env python3
"""
Smart content extraction for conversation-search
Uses hybrid approach: full user content + smart extraction for assistant messages
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class MessageSummarizer:
    """Handles smart hybrid extraction without AI summarization"""

    def __init__(self, db_path: str = "~/.conversation-search/index.db"):
        self.db_path = Path(db_path).expanduser()

    def is_tool_noise(self, message: Dict) -> bool:
        """
        Detect if message is pure tool spam that should be filtered

        Tool noise characteristics:
        - Pure tool markers with minimal text
        - Common read/search operations
        - Very short assistant acknowledgments
        """
        content = message['content']
        msg_type = message['message_type']

        # Pure tool noise - ONLY tool markers, no substantial content
        # Don't use this check, rely on the pattern matching below instead

        # Tool results are always noise
        if content.strip() == '[Tool result]':
            return True

        # Request interrupted messages
        if '[Request interrupted' in content:
            return True

        # Empty or whitespace-only content
        if not content.strip():
            return True

        # Very short messages that are just tool markers
        if len(content) < 50:
            return False  # These get marked as "too_short" instead

        # Common noise patterns with substantial text check
        noise_patterns = [
            '[Tool: Read]',
            '[Tool: Glob]',
            '[Tool: LS]',
            '[Tool: Grep]',
            '[Tool result]',
            '[Request interrupted]',
        ]

        if any(pattern in content for pattern in noise_patterns):
            # But allow if there's substantial text overall
            # Remove all tool markers and check remaining text
            text_without_tools = content
            for pattern in noise_patterns:
                text_without_tools = text_without_tools.replace(pattern, '')
            text_without_tools = text_without_tools.strip()

            if len(text_without_tools) > 100:
                return False
            return True

        # Assistant messages that are just acknowledging tool use
        if msg_type == 'assistant' and len(content) < 150:
            if any(phrase in content.lower() for phrase in [
                'let me read', 'let me check', 'let me search',
                "i'll look at", 'looking at', 'checking'
            ]):
                return True

        return False

    def get_searchable_text(self, message: Dict) -> str:
        """
        Extract searchable text using smart hybrid extraction

        Strategy:
        - User messages: index full content (they're concise, avg 3.5K chars)
        - Assistant messages: first 500 + last 200 chars + tool usage
        """
        content = message['content']
        msg_type = message['message_type']

        # User messages: usually concise, index full content
        if msg_type == 'user':
            return content  # Avg 3.5K chars, important info upfront

        # Assistant messages: verbose, extract strategically
        lines = content.split('\n')

        # Take first 500 chars
        first_part = content[:500] if len(content) > 500 else content

        # Extract tool mentions (important markers)
        tools = re.findall(r'\[Tool:\s*(\w+)\]', content)
        tool_summary = f"\nTools used: {', '.join(set(tools))}" if tools else ""

        # Last 200 chars often have conclusion
        last_part = ""
        if len(content) > 700:
            last_part = f"\n...\n{content[-200:]}"

        return f"{first_part}{tool_summary}{last_part}"

    def needs_summarization(self, message: Dict) -> Tuple[bool, str]:
        """
        Check if message needs processing (no AI, just classification)

        Returns: (needs_processing, reason)

        Reasons:
        - 'tool_noise': Pure tool spam, mark as noise
        - 'too_short': Message is < 50 chars
        - 'extract': Needs smart extraction (always for non-noise messages)
        """
        # Tool noise (check first, regardless of length)
        if self.is_tool_noise(message):
            return False, 'tool_noise'

        # Too short
        if len(message['content']) < 50:
            return False, 'too_short'

        # Everything else gets smart extraction
        return True, 'extract'

    def extract_batch(self, messages: List[Dict]) -> List[Dict]:
        """
        Extract searchable text from messages using smart hybrid extraction

        Returns: List of dicts with uuid, summary (extracted text)
        """
        if not messages:
            return []

        extractions = []
        for message in messages:
            extracted_text = self.get_searchable_text(message)
            extractions.append({
                'uuid': message['uuid'],
                'summary': extracted_text,
                'message_type': message['message_type']
            })

        return extractions

    def update_database(self, summaries: List[Dict], method: str = 'smart_extraction'):
        """Update database with extracted searchable text"""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        updated = 0
        try:
            for summary_data in summaries:
                uuid = summary_data.get('uuid')
                summary = summary_data.get('summary')

                if not uuid or not summary:
                    continue

                cursor.execute("""
                    UPDATE messages
                    SET summary = ?, is_summarized = TRUE, summary_method = ?
                    WHERE message_uuid = ?
                """, (summary, method, uuid))

                if cursor.rowcount > 0:
                    updated += 1

            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            print(f"Error updating summaries: {e}", file=sys.stderr)
            raise
        finally:
            conn.close()

        return updated

    def mark_tool_noise(self, message_uuids: List[str]):
        """Mark messages as tool noise in database"""
        if not message_uuids:
            return

        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        try:
            placeholders = ','.join('?' * len(message_uuids))
            cursor.execute(f"""
                UPDATE messages
                SET is_tool_noise = TRUE, summary_method = 'too_short'
                WHERE message_uuid IN ({placeholders})
            """, message_uuids)
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            print(f"Error marking tool noise: {e}", file=sys.stderr)
            raise
        finally:
            conn.close()

    def mark_too_short(self, message_uuids: List[str]):
        """Mark messages as too short to need summarization"""
        if not message_uuids:
            return

        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        try:
            placeholders = ','.join('?' * len(message_uuids))
            cursor.execute(f"""
                UPDATE messages
                SET is_summarized = TRUE, summary_method = 'too_short'
                WHERE message_uuid IN ({placeholders})
            """, message_uuids)
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            print(f"Error marking too short: {e}", file=sys.stderr)
            raise
        finally:
            conn.close()


def message_uses_conversation_search(message: Dict) -> bool:
    """
    Detect if a message involves using the conversation-search tool.

    Returns True if this is a Claude message that used the search tool.
    This helps identify meta-conversations that should be marked.

    Args:
        message: Message dict with 'message_type' and 'content'

    Returns:
        True if message uses conversation-search, False otherwise
    """
    # Only assistant messages can use tools
    if message.get('message_type') != 'assistant':
        return False

    content = message.get('content', '')
    content_lower = content.lower()

    # Pattern 1: Bash tool + cc-conversation-search command
    # This means Claude RAN the command via Bash
    if '[Tool: Bash]' in content and 'cc-conversation-search' in content:
        return True

    # Pattern 2: Direct cc-conversation-search command usage
    # Multiple patterns to catch various invocation styles
    if 'cc-conversation-search' in content:
        cmd_patterns = [
            # Direct subcommand: cc-conversation-search search
            r'cc-conversation-search\s+(search|list|index|tree|context|resume)',
            # Flags before subcommand: cc-conversation-search --json search
            r'cc-conversation-search\s+--\w+\s+(search|list|index|tree|context|resume)',
            # Version/help flags: cc-conversation-search --help
            r'cc-conversation-search\s+(--help|--version|-h|-v)',
        ]
        for pattern in cmd_patterns:
            if re.search(pattern, content):
                return True

    # Pattern 3: Tool upgrade commands
    if re.search(r'uv\s+tool\s+upgrade\s+cc-conversation-search', content):
        return True
    if re.search(r'pip\s+install\s+--upgrade\s+cc-conversation-search', content):
        return True

    # Pattern 4: Command existence checks
    if re.search(r'command\s+-v\s+cc-conversation-search', content):
        return True
    if re.search(r'which\s+cc-conversation-search', content):
        return True

    # Pattern 5: Skill activation markers (actual usage, not discussion)
    if 'conversation-search skill is loading' in content_lower:
        return True
    if 'conversation-search skill is running' in content_lower:
        return True

    # Pattern 6: The quoted skill name with activation verbs (more specific than before)
    if '"conversation-search"' in content_lower:
        activation_verbs = ['loading', 'running', 'is active', 'activated']
        if any(verb in content_lower for verb in activation_verbs):
            return True

    # Pattern 7: Skill allowed tools marker (with proximity check)
    if 'allowed 1 tools for this command' in content_lower:
        marker_pos = content_lower.find('allowed 1 tools')
        search_pos = content_lower.find('conversation-search')
        if search_pos != -1 and abs(marker_pos - search_pos) < 100:
            return True

    return False


def is_summarizer_conversation(conv_file: Path, messages: List[Dict]) -> bool:
    """
    Detect if this is an automated summarizer conversation

    Characteristics:
    - Very short (2-5 messages)
    - Contains summarization keywords
    - No tool use complexity
    """
    # Wrong length for summarizer
    if len(messages) < 2 or len(messages) > 10:
        return False

    # Check first user message for summarization patterns
    first_user = next((m for m in messages if m['message_type'] == 'user'), None)
    if not first_user:
        return False

    content = first_user['content'].lower()

    # Summarization keywords
    indicators = [
        'summarize this',
        'create a 1-2 sentence summary',
        'generate concise summaries',
        'max 150 characters',
        'for each message',
        'json output:',
        'brief summary here',
        'messages to summarize:',
    ]

    return any(indicator in content for indicator in indicators)
