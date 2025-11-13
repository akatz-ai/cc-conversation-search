#!/usr/bin/env python3
"""
Summarize and Index - Uses Claude Code Haiku agent for summarization
Called by the hook to incrementally index new messages
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import List, Dict


def get_recent_messages(conv_file: Path, last_n: int = 10) -> List[Dict]:
    """Extract the last N messages from a conversation file"""
    messages = []

    with open(conv_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())

                # Skip the summary line
                if line_num == 1 and data.get('type') == 'summary':
                    continue

                # Only process user/assistant messages
                if 'uuid' in data and 'message' in data:
                    msg_type = data.get('type')
                    if msg_type not in ('user', 'assistant'):
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
                                elif block.get('type') == 'tool_use':
                                    tool_name = block.get('name', 'unknown')
                                    text_parts.append(f"[Tool: {tool_name}]")
                        msg_content = '\n'.join(text_parts)

                    messages.append({
                        'uuid': data['uuid'],
                        'message_type': msg_type,
                        'content': msg_content,
                        'timestamp': data.get('timestamp'),
                        'session_id': data.get('sessionId')
                    })
            except json.JSONDecodeError:
                continue

    # Return last N messages
    return messages[-last_n:] if len(messages) > last_n else messages


def call_haiku_agent(messages: List[Dict], agent_path: Path) -> Dict:
    """
    Call Claude with Haiku model to generate summaries

    Returns dict with summaries: {"summaries": [{"uuid": "...", "summary": "..."}]}
    """
    # Prepare the prompt
    messages_json = json.dumps([{
        'uuid': m['uuid'],
        'message_type': m['message_type'],
        'content': m['content'][:2000]  # Truncate very long messages
    } for m in messages], indent=2)

    prompt = f"""You are a summarization assistant. Generate concise summaries for conversation messages.

Messages to summarize:
{messages_json}

For each message, create a 1-2 sentence summary (max 150 characters) that captures the main point.
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
        # Call claude CLI with haiku model
        result = subprocess.run(
            ['claude', '--model', 'haiku'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"Error calling claude: {result.stderr}", file=sys.stderr)
            return {"summaries": []}

        # Parse JSON from output
        output = result.stdout.strip()

        # Try to extract JSON (in case there's extra text)
        json_start = output.find('{')
        json_end = output.rfind('}') + 1

        if json_start >= 0 and json_end > json_start:
            json_str = output[json_start:json_end]
            return json.loads(json_str)
        else:
            print(f"No JSON found in output", file=sys.stderr)
            return {"summaries": []}

    except subprocess.TimeoutExpired:
        print("Claude call timed out", file=sys.stderr)
        return {"summaries": []}
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON output: {e}", file=sys.stderr)
        print(f"Output was: {result.stdout[:500]}", file=sys.stderr)
        return {"summaries": []}
    except Exception as e:
        print(f"Error calling claude: {e}", file=sys.stderr)
        return {"summaries": []}


def update_database_with_summaries(db_path: Path, summaries: List[Dict]):
    """Update existing messages in the database with new summaries"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    updated = 0
    for summary_data in summaries:
        uuid = summary_data.get('uuid')
        summary = summary_data.get('summary')

        if not uuid or not summary:
            continue

        # Update the summary for this message
        cursor.execute("""
            UPDATE messages
            SET summary = ?
            WHERE message_uuid = ?
        """, (summary, uuid))

        if cursor.rowcount > 0:
            updated += 1

    conn.commit()
    conn.close()

    return updated


def main():
    if len(sys.argv) < 2:
        print("Usage: summarize_and_index.py <conversation_file.jsonl> [num_messages]", file=sys.stderr)
        sys.exit(1)

    conv_file = Path(sys.argv[1])
    last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    if not conv_file.exists():
        print(f"Conversation file not found: {conv_file}", file=sys.stderr)
        sys.exit(1)

    # Paths
    script_dir = Path(__file__).parent.parent
    agent_path = script_dir / ".claude" / "agents" / "haiku-summary.md"
    db_path = Path.home() / ".claude-finder" / "index.db"

    if not agent_path.exists():
        print(f"Agent not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Run the indexer first: python3 src/indexer.py", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting last {last_n} messages from {conv_file.name}...")
    messages = get_recent_messages(conv_file, last_n)

    if not messages:
        print("No messages to summarize")
        sys.exit(0)

    print(f"Extracted {len(messages)} messages:")
    for msg in messages:
        print(f"  - {msg['uuid'][:8]}... ({msg['message_type']})")

    print(f"Calling Haiku agent to summarize {len(messages)} messages...")
    result = call_haiku_agent(messages, agent_path)

    summaries = result.get('summaries', [])
    if not summaries:
        print("No summaries generated")
        sys.exit(1)

    print(f"Got {len(summaries)} summaries from Haiku")
    if summaries:
        print(f"First summary: {summaries[0]}")

    print(f"Updating database with {len(summaries)} summaries...")
    updated = update_database_with_summaries(db_path, summaries)

    print(f"✓ Updated {updated} message summaries")


if __name__ == '__main__':
    main()
