"""Regression and bounded performance tests for incremental indexing."""

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from conversation_search import cli
from conversation_search.core.indexer import ConversationIndexer
from conversation_search.core.search import ConversationSearch


def write_session(path: Path, session_id: str, messages: int = 1, shared_uuid=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "summary", "summary": f"Synthetic {session_id}", "leafUuid": f"m-{messages - 1}"}]
    parent = None
    for number in range(messages):
        uuid = shared_uuid if number == 0 and shared_uuid else f"{session_id}-m-{number}"
        rows.append({
            "type": "user" if number % 2 == 0 else "assistant",
            "uuid": uuid,
            "parentUuid": parent,
            "sessionId": session_id,
            "timestamp": f"2026-08-28T12:00:{number:02d}Z",
            "message": {"content": f"synthetic message {number} for {session_id}"},
        })
        parent = uuid
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def make_indexer(tmp_path):
    projects = tmp_path / "projects"
    return ConversationIndexer(
        db_path=str(tmp_path / "index.db"),
        projects_dir=projects,
        quiet=True,
    ), projects


def test_unchanged_tree_is_metadata_only_and_fast(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    for number in range(500):
        session_id = f"00000000-0000-4000-8000-{number:012d}"
        write_session(projects / "-synthetic" / f"{session_id}.jsonl", session_id)

    first = indexer.index_changed(days_back=None, max_files=None, timeout_seconds=None)
    started = time.monotonic()
    second = indexer.index_changed(days_back=None, max_files=None, timeout_seconds=None)
    repeat_elapsed = time.monotonic() - started

    assert first.indexed == 500
    assert second.candidates == 0
    assert second.indexed == 0
    # This is deliberately generous for loaded CI; parsing 500 JSONL files would
    # be measurably slower and is separately excluded by the zero-candidate check.
    assert repeat_elapsed < 1.0
    indexer.close()


def test_depth_calculation_is_linear_for_large_conversation(tmp_path):
    indexer, _ = make_indexer(tmp_path)
    messages = [
        {
            "uuid": f"message-{number}",
            "parent_uuid": f"message-{number - 1}" if number else None,
        }
        for number in range(20_000)
    ]
    parent_map = {message["uuid"]: message["parent_uuid"] for message in messages}

    started = time.monotonic()
    depths = indexer.calculate_depth(messages, parent_map)
    elapsed = time.monotonic() - started

    assert depths["message-19999"] == 19_999
    assert elapsed < 1.0
    indexer.close()


def test_live_session_append_is_detected_and_idempotent(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "11111111-1111-4111-8111-111111111111"
    session_file = projects / "-live-project" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=1)

    assert indexer.index_changed(days_back=None).indexed == 1
    initial_size = session_file.stat().st_size
    with session_file.open("a") as handle:
        handle.write(json.dumps({
            "type": "assistant",
            "uuid": f"{session_id}-m-1",
            "parentUuid": f"{session_id}-m-0",
            "sessionId": session_id,
            "timestamp": "2026-08-28T12:00:01Z",
            "message": {"content": "synthetic appended message"},
        }) + "\n")
    _, appended = indexer.parse_conversation_file(session_file, initial_size)
    assert len(appended) == 1
    assert indexer.index_changed(days_back=None).indexed == 1
    assert indexer.index_changed(days_back=None).candidates == 0

    count = indexer.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    assert count == 2
    leaf = indexer.conn.execute(
        "SELECT leaf_message_uuid FROM conversations WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    assert leaf == "m-0"
    indexer.close()


def test_append_during_parse_is_retried_next_run(tmp_path, monkeypatch):
    indexer, projects = make_indexer(tmp_path)
    session_id = "12121212-1212-4212-8212-121212121212"
    session_file = projects / "-live-project" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=1)
    original_parse = indexer.parse_conversation_file

    def parse_then_append(path, start_offset=0):
        parsed = original_parse(path, start_offset)
        with path.open("a") as handle:
            handle.write(json.dumps({
                "type": "assistant",
                "uuid": f"{session_id}-late",
                "parentUuid": f"{session_id}-m-0",
                "sessionId": session_id,
                "timestamp": "2026-08-28T12:00:02Z",
                "message": {"content": "appended while parsing"},
            }) + "\n")
        return parsed

    monkeypatch.setattr(indexer, "parse_conversation_file", parse_then_append)
    assert indexer.index_conversation(session_file) is True
    monkeypatch.setattr(indexer, "parse_conversation_file", original_parse)

    assert indexer.scan_conversations(days_back=None, changed_only=True) == [session_file]
    assert indexer.index_changed(days_back=None).indexed == 1
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()[0] == 2
    indexer.close()


def test_incremental_meta_filter_marks_stored_ancestor_and_later_results(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "13131313-1313-4313-8313-131313131313"
    session_file = projects / "-meta" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=1)
    indexer.index_conversation(session_file)

    appended_rows = [
        {
            "type": "assistant", "uuid": "search-command",
            "parentUuid": f"{session_id}-m-0", "sessionId": session_id,
            "timestamp": "2026-08-28T12:00:01Z",
            "message": {"content": "[Tool: Bash]\ncc-conversation-search search old"},
        },
        {
            "type": "user", "uuid": "search-result", "parentUuid": "search-command",
            "sessionId": session_id, "timestamp": "2026-08-28T12:00:02Z",
            "message": {"content": "[Tool result]"},
        },
        {
            "type": "assistant", "uuid": "search-answer", "parentUuid": "search-result",
            "sessionId": session_id, "timestamp": "2026-08-28T12:00:03Z",
            "message": {"content": "Here is the old session."},
        },
    ]
    for row in appended_rows:
        with session_file.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        indexer.index_conversation(session_file)

    flags = {
        row['message_uuid']: row['is_meta_conversation']
        for row in indexer.conn.execute(
            "SELECT message_uuid, is_meta_conversation FROM messages"
        )
    }
    assert flags[f"{session_id}-m-0"] == 1
    assert flags['search-command'] == 1
    assert flags['search-result'] == 1
    assert flags['search-answer'] == 1

    followup = {
        "type": "user", "uuid": "real-followup", "parentUuid": "search-answer",
        "sessionId": session_id, "timestamp": "2026-08-28T12:00:04Z",
        "message": {"content": "Now implement the fix"},
    }
    with session_file.open("a") as handle:
        handle.write(json.dumps(followup) + "\n")
    indexer.index_conversation(session_file)
    assert indexer.conn.execute(
        "SELECT is_meta_conversation FROM messages WHERE message_uuid='real-followup'"
    ).fetchone()[0] == 0
    indexer.close()


def test_summarizer_classification_persists_across_appends(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "14141414-1414-4414-8414-141414141414"
    session_file = projects / "-summarizer" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=2)
    rows = session_file.read_text().splitlines()
    first_message = json.loads(rows[1])
    first_message['message']['content'] = 'Create a 1-2 sentence summary for each message'
    rows[1] = json.dumps(first_message)
    session_file.write_text("\n".join(rows) + "\n")

    indexer.index_conversation(session_file)
    with session_file.open("a") as handle:
        handle.write(json.dumps({
            "type": "assistant", "uuid": "later-tail",
            "parentUuid": f"{session_id}-m-1", "sessionId": session_id,
            "timestamp": "2026-08-28T12:00:03Z",
            "message": {"content": "ordinary-looking appended tail"},
        }) + "\n")
    indexer.index_conversation(session_file)

    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert indexer.conn.execute(
        "SELECT is_summarizer FROM indexed_files WHERE file_path = ?", (str(session_file),)
    ).fetchone()[0] == 1
    indexer.close()


@pytest.mark.parametrize("initial_content", [
    "",
    json.dumps({"type": "summary", "summary": "pending", "leafUuid": None}) + "\n",
])
def test_empty_or_summary_only_file_reclassifies_summarizer_pair(
    tmp_path, initial_content
):
    indexer, projects = make_indexer(tmp_path)
    session_id = "14343434-1434-4434-8434-143434343434"
    session_file = projects / "-summarizer" / f"{session_id}.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(initial_content)
    indexer.index_conversation(session_file)
    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0

    parent = None
    for kind, uuid, content in (
        ('user', 'summary-request', 'Summarize this in max 150 characters'),
        ('assistant', 'summary-response', 'A concise summary.'),
    ):
        with session_file.open("a") as handle:
            handle.write(json.dumps({
                "type": kind, "uuid": uuid, "parentUuid": parent,
                "sessionId": session_id, "timestamp": "2026-08-28T12:00:01Z",
                "message": {"content": content},
            }) + "\n")
        parent = uuid
    indexer.index_conversation(session_file)

    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert indexer.conn.execute(
        "SELECT is_summarizer FROM indexed_files WHERE file_path = ?", (str(session_file),)
    ).fetchone()[0] == 1
    indexer.close()


def test_incomplete_summarizer_is_reclassified_on_first_append(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "14444444-1444-4444-8444-144444444444"
    session_file = projects / "-summarizer" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=1)
    rows = session_file.read_text().splitlines()
    first = json.loads(rows[1])
    first['message']['content'] = 'Summarize this in max 150 characters'
    rows[1] = json.dumps(first)
    session_file.write_text("\n".join(rows) + "\n")
    indexer.index_conversation(session_file)
    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1

    with session_file.open("a") as handle:
        handle.write(json.dumps({
            "type": "assistant", "uuid": "summary-response",
            "parentUuid": f"{session_id}-m-0", "sessionId": session_id,
            "timestamp": "2026-08-28T12:00:01Z",
            "message": {"content": "A concise summary."},
        }) + "\n")
    indexer.index_conversation(session_file)

    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert indexer.conn.execute(
        "SELECT is_summarizer FROM indexed_files WHERE file_path = ?", (str(session_file),)
    ).fetchone()[0] == 1
    indexer.close()


def test_normal_session_suffix_cannot_reclassify_as_summarizer(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "14545454-1454-4454-8454-145454545454"
    session_file = projects / "-normal" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=1)
    indexer.index_conversation(session_file)

    parent = f"{session_id}-m-0"
    for number, (kind, content) in enumerate((
        ('user', 'Please summarize this ordinary discussion'),
        ('assistant', 'Here is the requested summary'),
        ('user', 'Continue with real work'),
    ), 1):
        uuid = f"normal-tail-{number}"
        with session_file.open("a") as handle:
            handle.write(json.dumps({
                "type": kind, "uuid": uuid, "parentUuid": parent,
                "sessionId": session_id,
                "timestamp": f"2026-08-28T12:00:0{number}Z",
                "message": {"content": content},
            }) + "\n")
        parent = uuid
        indexer.index_conversation(session_file)

    assert indexer.conn.execute(
        "SELECT is_summarizer FROM indexed_files WHERE file_path = ?", (str(session_file),)
    ).fetchone()[0] == 0
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()[0] == 4
    indexer.close()


def test_larger_rewrite_falls_back_to_full_reconciliation(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    old_session = "15151515-1515-4515-8515-151515151515"
    new_session = "16161616-1616-4616-8616-161616161616"
    session_file = projects / "-rewrite" / f"{old_session}.jsonl"
    write_session(session_file, old_session, messages=1)
    indexer.index_conversation(session_file)

    write_session(session_file, new_session, messages=3)
    indexer.index_conversation(session_file)

    sessions = {
        row[0] for row in indexer.conn.execute("SELECT session_id FROM conversations")
    }
    assert sessions == {new_session}
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (new_session,)
    ).fetchone()[0] == 3
    indexer.close()


def test_early_prefix_rewrite_plus_append_reconciles_stale_content(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "17171717-1717-4717-8717-171717171717"
    session_file = projects / "-prefix-rewrite" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=2)
    rows = session_file.read_text().splitlines()
    first = json.loads(rows[1])
    first['message']['content'] = 'oldtoken' + ('x' * 10_000)
    rows[1] = json.dumps(first)
    session_file.write_text("\n".join(rows) + "\n")
    indexer.index_conversation(session_file)

    rewritten = session_file.read_text().replace('oldtoken', 'newtoken', 1)
    appended = {
        "type": "assistant", "uuid": "rewrite-tail",
        "parentUuid": f"{session_id}-m-1", "sessionId": session_id,
        "timestamp": "2026-08-28T12:00:03Z",
        "message": {"content": "appended after earlier redaction"},
    }
    session_file.write_text(rewritten + json.dumps(appended) + "\n")
    indexer.index_conversation(session_file)

    content = indexer.conn.execute(
        "SELECT full_content FROM messages WHERE message_uuid = ?",
        (f"{session_id}-m-0",),
    ).fetchone()[0]
    assert 'newtoken' in content
    assert 'oldtoken' not in content
    indexer.close()


def test_empty_rewrite_removes_previously_searchable_conversation(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "18181818-1818-4818-8818-181818181818"
    session_file = projects / "-empty-rewrite" / f"{session_id}.jsonl"
    write_session(session_file, session_id)
    indexer.index_conversation(session_file)

    session_file.write_text("")
    indexer.index_conversation(session_file)

    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert indexer.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    indexer.close()


def test_exact_session_lookup_indexes_only_target(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    target = "22222222-2222-4222-8222-222222222222"
    write_session(projects / "-target" / f"{target}.jsonl", target, messages=2)
    for number in range(100):
        other = f"33333333-3333-4333-8333-{number:012d}"
        write_session(projects / "-distractors" / f"{other}.jsonl", other)

    target_file = indexer.find_session_file(target)
    assert target_file == projects / "-target" / f"{target}.jsonl"
    assert indexer.index_conversation(target_file) is True
    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
    indexer.close()

    search = ConversationSearch(db_path=str(tmp_path / "index.db"))
    result = search.find_exact_session(target)
    assert len(result) == 1
    assert result[0]["session_id"] == target
    assert result[0]["project_path"] == "/target"
    assert result[0]["context_snippet"] == f"Synthetic {target}"
    assert "synthetic message" not in result[0]["context_snippet"]
    search.close()


def test_auto_index_exact_id_never_runs_broad_index(monkeypatch, tmp_path):
    target = tmp_path / "exact.jsonl"
    calls = []

    class FakeIndexer:
        def __init__(self, quiet):
            calls.append(("init", quiet))

        def find_session_file(self, session_id):
            calls.append(("find", session_id))
            return target

        def index_conversation(self, path):
            calls.append(("index", path))

        def index_changed(self, **kwargs):
            raise AssertionError("exact-session path must not broadly index")

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(cli, "ConversationIndexer", FakeIndexer)
    session_id = "23232323-2323-4232-8232-232323232323"
    cli._auto_index(SimpleNamespace(), 30, exact_session_id=session_id)

    assert calls == [
        ("init", True),
        ("find", session_id),
        ("index", target),
        ("close",),
    ]


def test_cli_normalizes_whitespace_around_exact_session_id(monkeypatch, capsys):
    session_id = "25252525-2525-4252-8252-252525252525"
    observed = []

    monkeypatch.setattr(
        cli,
        "_auto_index",
        lambda args, days, exact_session_id=None: observed.append((days, exact_session_id)),
    )

    class FakeSearch:
        def find_exact_session(self, exact):
            observed.append(("search", exact))
            return [{"session_id": exact}]

        def search_conversations(self, **kwargs):
            raise AssertionError("exact ID must not use FTS")

    monkeypatch.setattr(cli, "ConversationSearch", FakeSearch)
    args = SimpleNamespace(
        query=f"  {session_id}  ", no_index=False, days=None, since=None,
        until=None, date=None, limit=20, project=None, json=True,
    )
    cli.cmd_search(args)

    assert observed == [(30, session_id), ("search", session_id)]
    assert json.loads(capsys.readouterr().out)[0]["session_id"] == session_id


def test_zero_timeout_bounds_discovery_before_opening_files(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    session_id = "24242424-2424-4242-8242-242424242424"
    write_session(projects / "-deadline" / f"{session_id}.jsonl", session_id)

    result = indexer.index_changed(days_back=None, timeout_seconds=0)
    assert result.indexed == 0
    assert result.truncated is True
    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    indexer.close()


def test_index_budget_is_bounded_and_reports_truncation(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    for number in range(10):
        session_id = f"44444444-4444-4444-8444-{number:012d}"
        write_session(projects / "-bounded" / f"{session_id}.jsonl", session_id)

    result = indexer.index_changed(days_back=None, max_files=3, timeout_seconds=None)
    assert result.candidates == 10
    assert result.indexed == 3
    assert result.truncated is True
    assert indexer.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 3
    indexer.close()


def test_concurrent_indexers_do_not_race_unique_inserts(tmp_path):
    db_path = tmp_path / "index.db"
    projects = tmp_path / "projects"
    session_id = "45454545-4545-4545-8545-454545454545"
    session_file = projects / "-concurrent" / f"{session_id}.jsonl"
    write_session(session_file, session_id, messages=3)
    # Initialize schema before the concurrent workers start migrating triggers.
    ConversationIndexer(db_path=str(db_path), projects_dir=projects, quiet=True).close()
    barrier = Barrier(2)

    def index_in_own_thread(_):
        indexer = ConversationIndexer(db_path=str(db_path), projects_dir=projects, quiet=True)
        original = indexer.parse_conversation_file

        def synchronized_parse(path, start_offset=0):
            parsed = original(path, start_offset)
            barrier.wait(timeout=5)
            return parsed

        indexer.parse_conversation_file = synchronized_parse
        try:
            return indexer.index_conversation(session_file)
        finally:
            indexer.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(index_in_own_thread, range(2)))

    assert outcomes == [True, True]
    verifier = ConversationIndexer(db_path=str(db_path), projects_dir=projects, quiet=True)
    assert verifier.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
    verifier.close()


def test_repeated_uuid_is_idempotent_instead_of_raising(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    shared = "shared-message-uuid"
    first = "55555555-5555-4555-8555-555555555555"
    second = "66666666-6666-4666-8666-666666666666"
    write_session(projects / "-imports" / f"{first}.jsonl", first, shared_uuid=shared)
    write_session(projects / "-imports" / f"{second}.jsonl", second, shared_uuid=shared)

    result = indexer.index_changed(days_back=None, max_files=None, timeout_seconds=None)
    assert result.failed == 0
    assert result.indexed == 2
    assert indexer.index_changed(days_back=None).candidates == 0
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM messages WHERE message_uuid = ?", (shared,)
    ).fetchone()[0] == 1
    indexer.close()


def test_legacy_database_adds_meta_column_before_index(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE messages (
            message_uuid TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            parent_uuid TEXT, is_sidechain BOOLEAN DEFAULT FALSE,
            depth INTEGER DEFAULT 0, timestamp TEXT NOT NULL,
            message_type TEXT NOT NULL CHECK(message_type IN ('user', 'assistant')),
            project_path TEXT, conversation_file TEXT, summary TEXT,
            full_content TEXT NOT NULL, is_summarized BOOLEAN DEFAULT FALSE,
            is_tool_noise BOOLEAN DEFAULT FALSE,
            summary_method TEXT, indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    migrated = ConversationIndexer(
        db_path=str(db_path), projects_dir=tmp_path / "projects", quiet=True
    )
    columns = {
        row['name'] for row in migrated.conn.execute("PRAGMA table_info(messages)")
    }
    indexes = {
        row['name'] for row in migrated.conn.execute("PRAGMA index_list(messages)")
    }
    assert 'is_meta_conversation' in columns
    assert 'idx_is_meta_conversation' in indexes
    migrated.close()


def test_legacy_fts_trigger_migration_rebuilds_existing_index(tmp_path):
    indexer, projects = make_indexer(tmp_path)
    indexer.conn.execute("""
        INSERT INTO messages(message_uuid, session_id, timestamp, message_type, full_content)
        VALUES ('legacy-message', 'legacy-session', '2026-08-28T12:00:00Z', 'user', 'repairword')
    """)
    row = indexer.conn.execute(
        "SELECT rowid, message_uuid, full_content FROM messages WHERE message_uuid='legacy-message'"
    ).fetchone()
    indexer.conn.execute("""
        INSERT INTO message_content_fts(message_content_fts, rowid, message_uuid, full_content)
        VALUES ('delete', ?, ?, ?)
    """, (row['rowid'], row['message_uuid'], row['full_content']))
    indexer.conn.execute("DROP TABLE indexed_files")
    indexer.conn.execute("""
        CREATE TABLE indexed_files (
            file_path TEXT PRIMARY KEY,
            session_id TEXT,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL
        )
    """)
    indexer.conn.execute("DROP TRIGGER messages_ad")
    indexer.conn.execute("DROP TRIGGER messages_au")
    indexer.conn.execute("""
        CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
            DELETE FROM message_content_fts WHERE rowid = old.rowid;
        END
    """)
    indexer.conn.execute("""
        CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
            DELETE FROM message_content_fts WHERE rowid = old.rowid;
            INSERT INTO message_content_fts(rowid, message_uuid, full_content)
            VALUES (new.rowid, new.message_uuid, new.full_content);
        END
    """)
    indexer.conn.commit()
    indexer.close()

    def initialize(_):
        concurrent = ConversationIndexer(
            db_path=str(tmp_path / "index.db"), projects_dir=projects, quiet=True
        )
        concurrent.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(initialize, range(2)))

    migrated = ConversationIndexer(
        db_path=str(tmp_path / "index.db"), projects_dir=projects, quiet=True
    )
    assert migrated.conn.execute(
        "SELECT COUNT(*) FROM message_content_fts WHERE full_content MATCH 'repairword'"
    ).fetchone()[0] == 1
    trigger_sql = migrated.conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='messages_ad'"
    ).fetchone()[0]
    assert "DELETE FROM message_content_fts" not in trigger_sql
    migrated.close()


def test_fts_update_and_delete_triggers_remain_consistent(tmp_path):
    indexer, _ = make_indexer(tmp_path)
    indexer.conn.execute("""
        INSERT INTO messages(message_uuid, session_id, timestamp, message_type, full_content)
        VALUES ('fts-message', 'fts-session', '2026-08-28T12:00:00Z', 'user', 'beforeword')
    """)
    indexer.conn.execute(
        "UPDATE messages SET full_content = 'afterword' WHERE message_uuid = 'fts-message'"
    )
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM message_content_fts WHERE full_content MATCH 'afterword'"
    ).fetchone()[0] == 1
    indexer.conn.execute("DELETE FROM messages WHERE message_uuid = 'fts-message'")
    indexer.conn.commit()
    assert indexer.conn.execute(
        "SELECT COUNT(*) FROM message_content_fts WHERE full_content MATCH 'afterword'"
    ).fetchone()[0] == 0
    indexer.close()
