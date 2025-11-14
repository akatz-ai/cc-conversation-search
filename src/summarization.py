#!/usr/bin/env python3
"""
Shared summarization logic for claude-finder
Uses Claude Code CLI in headless mode for batch message summarization
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class MessageSummarizer:
    """Handles batch message summarization using Claude Code CLI"""

    def __init__(self, db_path: str = "~/.claude-finder/index.db"):
        self.db_path = Path(db_path).expanduser()
        self.workspace_dir = Path.home() / ".claude-finder" / "summarizer-workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

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

        # Aggressive tool noise detection - if it starts with [Tool, it's noise
        if content.strip().startswith('[Tool'):
            return True

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
            # But allow if there's substantial text after the tool
            text_after_tool = content.split(']', 1)[-1].strip()
            if len(text_after_tool) > 100:
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

    def is_truncated_summary(self, summary: str, full_content: str = "") -> bool:
        """Detect if summary is just truncated content vs AI-generated"""
        if not summary:
            return True

        return (
            summary.endswith('...') or
            (145 <= len(summary) <= 150 and len(full_content) > len(summary)) or
            summary.startswith('[Tool') or
            len(summary) < 20
        )

    def needs_summarization(self, message: Dict) -> Tuple[bool, str]:
        """
        Check if message needs AI summarization

        Returns: (needs_summary, reason)

        Reasons:
        - 'too_short': Message is < 50 chars, use raw content
        - 'tool_noise': Pure tool spam, mark as noise
        - 'truncated': Has truncated summary, needs regeneration
        - 'already_done': Has AI summary already
        """
        content = message['content']
        summary = message.get('summary', '')

        # Tool noise (check first, regardless of length)
        if self.is_tool_noise(message):
            return False, 'tool_noise'

        # Too short to bother
        if len(content) < 50:
            return False, 'too_short'

        # Check if already has good summary
        if summary and not self.is_truncated_summary(summary, content):
            # Has a good summary already
            return False, 'already_done'

        # Needs summarization
        return True, 'needs_summary'

    def summarize_batch(self, messages: List[Dict]) -> List[Dict]:
        """
        Batch summarize messages using Claude Code CLI

        Returns: List of dicts with uuid, summary, is_tool_noise
        """
        if not messages:
            return []

        # Prepare batch prompt
        messages_json = json.dumps([{
            'uuid': m['uuid'],
            'message_type': m['message_type'],
            'content': m['content'][:2000]  # Truncate very long messages
        } for m in messages], indent=2)

        prompt = f"""Generate concise summaries for conversation messages.

Messages to summarize:
{messages_json}

For each message, create a 1-2 sentence summary (max 150 characters).
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
            # Run Claude Code in headless mode from summarizer workspace
            result = subprocess.run(
                ['claude', '-p', '--model', 'haiku', '--output-format', 'json'],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=str(self.workspace_dir),
                timeout=60
            )

            if result.returncode != 0:
                print(f"Error calling Claude: {result.stderr}", file=sys.stderr)
                return []

            # Parse JSON output
            data = json.loads(result.stdout)
            response_text = data.get('result', '')

            # Extract JSON from response (in case there's extra text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                summaries_data = json.loads(json_str)
                return summaries_data.get('summaries', [])

            return []

        except subprocess.TimeoutExpired:
            print("Claude call timed out", file=sys.stderr)
            return []
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Error in batch summarization: {e}", file=sys.stderr)
            return []

    def update_database(self, summaries: List[Dict], method: str = 'ai_generated'):
        """Update database with new summaries and metadata"""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        updated = 0
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
        conn.close()

        return updated

    def mark_tool_noise(self, message_uuids: List[str]):
        """Mark messages as tool noise in database"""
        if not message_uuids:
            return

        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(message_uuids))
        cursor.execute(f"""
            UPDATE messages
            SET is_tool_noise = TRUE, summary_method = 'too_short'
            WHERE message_uuid IN ({placeholders})
        """, message_uuids)

        conn.commit()
        conn.close()

    def mark_too_short(self, message_uuids: List[str]):
        """Mark messages as too short to need summarization"""
        if not message_uuids:
            return

        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(message_uuids))
        cursor.execute(f"""
            UPDATE messages
            SET is_summarized = TRUE, summary_method = 'too_short'
            WHERE message_uuid IN ({placeholders})
        """, message_uuids)

        conn.commit()
        conn.close()


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
