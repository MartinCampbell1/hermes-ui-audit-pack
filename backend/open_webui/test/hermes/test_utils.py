import json
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from open_webui.models.chats import Chat
from open_webui.utils.hermes import (
    HERMES_RUNNER_RESULT_SENTINEL,
    SYSTEM_PYTHON_WARNING,
    _build_hermes_message_with_attachments,
    build_hermes_context_summary,
    browse_hermes_workspace,
    build_chat_import_payload,
    discover_hermes_agent_dir,
    discover_hermes_python,
    get_hermes_workspace_file_path,
    get_active_hermes_home,
    get_active_profile_name,
    get_hermes_profiles,
    get_hermes_sessions,
    get_hermes_workspaces,
    get_imported_hermes_chat_map,
    load_hermes_session,
    resolve_base_hermes_home,
    send_hermes_runner_control_message,
    send_hermes_session_message,
    start_hermes_session_message_process,
    switch_hermes_profile,
    switch_hermes_workspace,
)


def _create_state_db(path: Path):
    connection = sqlite3.connect(path)
    cursor = connection.cursor()
    cursor.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            model TEXT,
            started_at REAL NOT NULL,
            message_count INTEGER DEFAULT 0,
            title TEXT
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            reasoning TEXT,
            reasoning_details TEXT
        );
        """
    )
    connection.commit()
    connection.close()


def _build_imported_chat(
    chat_id: str,
    session_id: str,
    title: str,
    updated_at: int,
    *,
    include_meta: bool = True,
    archived: bool = False,
) -> Chat:
    chat_payload = {
        'title': title,
        'models': [],
        'history': {'messages': {}, 'currentId': None},
        'messages': [],
        'params': {},
        'files': [],
        'tags': [],
        'timestamp': updated_at * 1000,
        'hermesSession': {'session_id': session_id, 'source': 'hermes_cli'},
    }

    return Chat(
        id=chat_id,
        user_id='user-1',
        title=title,
        chat=chat_payload,
        meta={'hermes': {'session_id': session_id, 'source': 'hermes_cli'}} if include_meta else {},
        created_at=updated_at - 10,
        updated_at=updated_at,
        archived=archived,
        pinned=False,
    )


def test_resolve_base_home_uses_profile_parent(monkeypatch, tmp_path):
    profile_home = tmp_path / 'profiles' / 'work'
    profile_home.mkdir(parents=True)

    monkeypatch.setenv('HERMES_HOME', str(profile_home))
    monkeypatch.delenv('HERMES_BASE_HOME', raising=False)

    assert resolve_base_hermes_home() == tmp_path


def test_active_profile_infers_name_from_hermes_home_profile(monkeypatch, tmp_path):
    profile_home = tmp_path / 'profiles' / 'work'
    profile_home.mkdir(parents=True)

    monkeypatch.setenv('HERMES_HOME', str(profile_home))
    monkeypatch.delenv('HERMES_BASE_HOME', raising=False)

    assert resolve_base_hermes_home() == tmp_path
    assert get_active_profile_name() == 'work'
    assert get_active_hermes_home() == profile_home


def test_active_home_reads_active_profile(monkeypatch, tmp_path):
    (tmp_path / 'profiles' / 'work').mkdir(parents=True)
    (tmp_path / 'active_profile').write_text('work', encoding='utf-8')

    monkeypatch.setenv('HERMES_BASE_HOME', str(tmp_path))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    assert get_active_profile_name() == 'work'
    assert get_active_hermes_home() == tmp_path / 'profiles' / 'work'


def test_active_profile_falls_back_to_profile_hermes_home(monkeypatch, tmp_path):
    profile_home = tmp_path / '.hermes' / 'profiles' / 'work'
    profile_home.mkdir(parents=True)

    monkeypatch.delenv('HERMES_BASE_HOME', raising=False)
    monkeypatch.setenv('HERMES_HOME', str(profile_home))

    assert get_active_profile_name() == 'work'
    assert get_active_hermes_home() == profile_home


def test_get_hermes_profiles_reads_default_profile_context(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    memories_dir = hermes_home / 'memories'
    skill_dir = hermes_home / 'skills' / 'planner'
    hidden_skill_dir = hermes_home / 'skills' / '.hub' / 'hidden'
    memories_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    hidden_skill_dir.mkdir(parents=True)

    (hermes_home / 'config.yaml').write_text(
        (
            'model:\n'
            '  default: gpt-5.4\n'
            '  provider: openai-codex\n'
            'memory:\n'
            '  memory_enabled: true\n'
            '  user_profile_enabled: true\n'
        ),
        encoding='utf-8',
    )
    (hermes_home / '.env').write_text('OPENAI_API_KEY=redacted\n', encoding='utf-8')
    (hermes_home / 'SOUL.md').write_text('# Soul\n', encoding='utf-8')
    (memories_dir / 'MEMORY.md').write_text('# Memory\n', encoding='utf-8')
    (memories_dir / 'USER.md').write_text('# User\n', encoding='utf-8')
    (skill_dir / 'SKILL.md').write_text('# Skill\n', encoding='utf-8')
    (hidden_skill_dir / 'SKILL.md').write_text('# Hidden\n', encoding='utf-8')

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    payload = get_hermes_profiles()

    assert payload['active_home'] == str(hermes_home)
    assert payload['active_profile'] == 'default'
    assert payload['items'] == [
        {
            'name': 'default',
            'path': str(hermes_home),
            'is_default': True,
            'is_active': True,
            'model': 'gpt-5.4',
            'provider': 'openai-codex',
            'has_env': True,
            'has_soul': True,
            'has_memory': True,
            'has_user_profile': True,
            'memory_enabled': True,
            'user_profile_enabled': True,
            'gateway_running': False,
            'skill_count': 1,
        }
    ]


def test_build_hermes_context_summary_prefers_session_model(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    hermes_home.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        'model:\n  default: claude-sonnet\n  provider: anthropic\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    summary = build_hermes_context_summary(
        {
            'target_id': 'local',
            'normalized_session_id': 'session-1',
            'workspace_path': str(tmp_path / 'workspace'),
            'resolved_model': 'gpt-5.4',
            'files': [{'name': 'plan.md'}, {'name': 'notes.md'}],
            'runtime': {'active_profile': 'default'},
            'session_payload': {
                'session_id': 'session-1',
                'model': 'gpt-5.4',
            },
        }
    )

    assert summary == {
        'target_id': 'local',
        'active_profile': 'default',
        'workspace_path': str(tmp_path / 'workspace'),
        'attached_file_count': 2,
        'model': 'gpt-5.4',
        'model_source': 'session',
        'session_id': 'session-1',
    }


def test_get_hermes_profiles_marks_named_active_profile(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    profile_home = hermes_home / 'profiles' / 'work'
    profile_home.mkdir(parents=True)
    (hermes_home / 'active_profile').write_text('work', encoding='utf-8')
    (profile_home / 'config.yaml').write_text(
        'model:\n  default: gpt-5.4-mini\n  provider: openai-codex\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    payload = get_hermes_profiles()
    profile_map = {profile['name']: profile for profile in payload['items']}

    assert payload['active_home'] == str(profile_home)
    assert payload['active_profile'] == 'work'
    assert profile_map['default']['is_default'] is True
    assert profile_map['default']['is_active'] is False
    assert profile_map['work']['is_default'] is False
    assert profile_map['work']['is_active'] is True
    assert profile_map['work']['model'] == 'gpt-5.4-mini'
    assert profile_map['work']['provider'] == 'openai-codex'


def test_switch_hermes_profile_updates_active_profile_context(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    profile_home = hermes_home / 'profiles' / 'work'
    profile_workspace = tmp_path / 'profile-workspace'
    profile_workspace.mkdir(parents=True)
    profile_home.mkdir(parents=True)
    (profile_home / 'config.yaml').write_text(
        (
            'model:\n'
            '  default: gpt-5.4-mini\n'
            '  provider: openai-codex\n'
            f'terminal:\n  cwd: "{profile_workspace}"\n'
        ),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    payload = switch_hermes_profile('work')
    profile_map = {profile['name']: profile for profile in payload['items']}

    assert (hermes_home / 'active_profile').read_text(encoding='utf-8') == 'work'
    assert os.environ['HERMES_HOME'] == str(profile_home)
    assert get_active_profile_name() == 'work'
    assert get_active_hermes_home() == profile_home
    assert payload['active_profile'] == 'work'
    assert payload['active_home'] == str(profile_home)
    assert payload['default_model'] == 'gpt-5.4-mini'
    assert payload['default_workspace'] == str(profile_workspace.resolve())
    assert profile_map['work']['is_active'] is True

    default_payload = switch_hermes_profile('default')

    assert (hermes_home / 'active_profile').read_text(encoding='utf-8') == ''
    assert os.environ['HERMES_HOME'] == str(hermes_home)
    assert default_payload['active_profile'] == 'default'
    assert default_payload['active_home'] == str(hermes_home)


def test_switch_hermes_profile_rejects_missing_or_invalid_profile(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    hermes_home.mkdir(parents=True)

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    with pytest.raises(ValueError):
        switch_hermes_profile('../bad')

    with pytest.raises(FileNotFoundError):
        switch_hermes_profile('missing')


def test_discover_agent_dir_prefers_env_override(monkeypatch, tmp_path):
    env_agent = tmp_path / 'env-agent'
    env_agent.mkdir()
    (env_agent / 'run_agent.py').write_text('#!/usr/bin/env python3\n', encoding='utf-8')

    fallback_agent = tmp_path / '.hermes' / 'hermes-agent'
    fallback_agent.mkdir(parents=True)
    (fallback_agent / 'run_agent.py').write_text('#!/usr/bin/env python3\n', encoding='utf-8')

    monkeypatch.setenv('HERMES_WEBUI_AGENT_DIR', str(env_agent))
    monkeypatch.setenv('HERMES_BASE_HOME', str(tmp_path / '.hermes'))

    assert discover_hermes_agent_dir(repo_root=tmp_path) == env_agent.resolve()


def test_discover_python_prefers_agent_venv(tmp_path, monkeypatch):
    agent_dir = tmp_path / 'hermes-agent'
    python_path = agent_dir / '.venv' / 'bin' / 'python'
    python_path.parent.mkdir(parents=True)
    python_path.write_text('', encoding='utf-8')

    monkeypatch.delenv('HERMES_WEBUI_PYTHON', raising=False)
    monkeypatch.delenv('HERMES_PYTHON', raising=False)

    discovered, warnings = discover_hermes_python(agent_dir=agent_dir, repo_root=tmp_path)

    assert discovered == str(python_path)
    assert warnings == []


def test_discover_python_warns_on_system_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv('HERMES_WEBUI_PYTHON', raising=False)
    monkeypatch.delenv('HERMES_PYTHON', raising=False)
    monkeypatch.setattr('open_webui.utils.hermes.shutil.which', lambda name: '/usr/bin/python3')

    discovered, warnings = discover_hermes_python(agent_dir=None, repo_root=tmp_path)

    assert discovered == '/usr/bin/python3'
    assert warnings == [SYSTEM_PYTHON_WARNING]


def test_get_hermes_sessions_merges_state_db_and_json(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    _create_state_db(hermes_home / 'state.db')
    with sqlite3.connect(hermes_home / 'state.db') as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source, model, started_at, message_count, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('abc123', 'cli', 'gpt-5.4', 1000.0, 2, ''),
        )
        cursor.executemany(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            [
                ('abc123', 'user', 'first prompt', 1001.0),
                ('abc123', 'assistant', 'reply', 1002.0),
            ],
        )
        connection.commit()

    (sessions_dir / 'session_abc123.json').write_text(
        """
        {
          "session_id": "abc123",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "message_count": 4,
          "messages": [
            {"role": "user", "content": "first prompt"},
            {"role": "assistant", "content": "reply"}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert payload['active_home'] == str(hermes_home)
    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'abc123'
    assert payload['items'][0]['message_count'] == 4
    assert set(payload['items'][0]['available_sources']) == {'json', 'state_db'}
    assert payload['items'][0]['is_auxiliary_cli_session'] is False


def test_get_hermes_sessions_keeps_json_preview_as_canonical_when_state_db_is_fresher(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    _create_state_db(hermes_home / 'state.db')
    with sqlite3.connect(hermes_home / 'state.db') as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source, model, started_at, message_count, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('abc123', 'cli', 'gpt-5.4', 1000.0, 3, 'DB Title'),
        )
        cursor.executemany(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            [
                ('abc123', 'user', 'db-only stale mirror should not become canonical', 1009.0),
                ('abc123', 'assistant', 'reply', 1010.0),
            ],
        )
        connection.commit()

    json_path = sessions_dir / 'session_abc123.json'
    json_path.write_text(
        json.dumps(
            {
                'session_id': 'abc123',
                'title': 'JSON Title',
                'model': 'gpt-5.4',
                'session_start': 1000,
                'last_updated': 1005,
                'message_count': 2,
                'messages': [
                    {'role': 'user', 'content': 'canonical json prompt'},
                    {'role': 'assistant', 'content': 'canonical json reply'},
                ],
            }
        ),
        encoding='utf-8',
    )
    os.utime(json_path, (1005, 1005))

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()

    assert payload['items'][0]['session_id'] == 'abc123'
    assert payload['items'][0]['updated_at'] == 1010
    assert payload['items'][0]['title'] == 'JSON Title'
    assert payload['items'][0]['last_user_content'] == 'canonical json prompt'
    assert payload['items'][0]['source_tag'] == 'cli'
    assert set(payload['items'][0]['available_sources']) == {'json', 'state_db'}


def test_get_hermes_sessions_uses_practical_default_limit_and_respects_explicit_limit(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    for index in range(101):
        session_id = f'limit{index:03d}'
        timestamp = 1000 + index
        json_path = sessions_dir / f'session_{session_id}.json'
        json_path.write_text(
            json.dumps(
                {
                    'session_id': session_id,
                    'model': 'gpt-5.4',
                    'session_start': 1000,
                    'last_updated': timestamp,
                    'message_count': 1,
                    'messages': [
                        {'role': 'user', 'content': f'question {index}'},
                        {'role': 'assistant', 'content': 'reply'},
                    ],
                }
            ),
            encoding='utf-8',
        )
        os.utime(json_path, (timestamp, timestamp))

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()
    limited_payload = get_hermes_sessions(limit=7)

    assert len(payload['items']) == 101
    assert payload['items'][0]['session_id'] == 'limit100'
    assert len(limited_payload['items']) == 7
    assert limited_payload['items'][0]['session_id'] == 'limit100'


def test_get_hermes_sessions_uses_message_timestamp_and_file_mtime_for_json_freshness(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    stale_path = sessions_dir / 'session_stale-metadata.json'
    stale_path.write_text(
        json.dumps(
            {
                'session_id': 'stale-metadata',
                'model': 'gpt-5.4',
                'session_start': 1000,
                'last_updated': 1001,
                'messages': [
                    {'role': 'user', 'content': 'fresh message timestamp', 'timestamp': 2000},
                ],
            }
        ),
        encoding='utf-8',
    )
    os.utime(stale_path, (1500, 1500))
    mtime_path = sessions_dir / 'session_mtime-fallback.json'
    mtime_path.write_text(
        json.dumps(
            {
                'session_id': 'mtime-fallback',
                'model': 'gpt-5.4',
                'session_start': 1000,
                'messages': [
                    {'role': 'user', 'content': 'mtime fallback'},
                ],
            }
        ),
        encoding='utf-8',
    )
    os.utime(mtime_path, (3000, 3000))

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()

    assert [item['session_id'] for item in payload['items']] == [
        'mtime-fallback',
        'stale-metadata',
    ]
    assert payload['items'][0]['updated_at'] == 3000
    assert payload['items'][1]['updated_at'] == 2000


def test_get_hermes_sessions_marks_auxiliary_cli_json_session(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / 'session_aux123.json').write_text(
        """
        {
          "session_id": "aux123",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "message_count": 2,
          "messages": [
            {"role": "user", "content": "Inspect codex-local-router and propose the next bounded implementation slice."},
            {"role": "assistant", "content": "worker result"}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'aux123'
    assert payload['items'][0]['is_auxiliary_cli_session'] is True


def test_get_hermes_sessions_marks_generated_prompt_only_json_session_auxiliary(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / 'session_generated123.json').write_text(
        """
        {
          "session_id": "generated123",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "message_count": 2,
          "messages": [
            {"role": "user", "content": "Review the conversation above and consider saving or updating a skill if appropriate."},
            {"role": "assistant", "content": "Nothing to save."}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'generated123'
    assert payload['items'][0]['is_auxiliary_cli_session'] is True


def test_get_hermes_sessions_marks_memory_compiler_prompt_only_json_session_auxiliary(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / 'session_memory123.json').write_text(
        """
        {
          "session_id": "memory123",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "message_count": 2,
          "messages": [
            {"role": "user", "content": "You are Hermes Memory's structured wiki compiler. Return exactly one JSON object and nothing else."},
            {"role": "assistant", "content": "{}"}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'memory123'
    assert payload['items'][0]['is_auxiliary_cli_session'] is True


def test_get_hermes_sessions_keeps_normal_multi_turn_json_visible(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / 'session_main123.json').write_text(
        """
        {
          "session_id": "main123",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "message_count": 4,
          "messages": [
            {"role": "user", "content": "Давай продолжим с того места, где остановились."},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "Покажи следующий шаг."},
            {"role": "assistant", "content": "step"}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'main123'
    assert payload['items'][0]['is_auxiliary_cli_session'] is False


def test_get_hermes_sessions_keeps_state_db_only_session_unflagged(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    hermes_home.mkdir(parents=True)

    _create_state_db(hermes_home / 'state.db')
    with sqlite3.connect(hermes_home / 'state.db') as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source, model, started_at, message_count, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('state123', 'cli', 'gpt-5.4', 1000.0, 1, 'Hermes Session'),
        )
        connection.execute(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            ('state123', 'user', 'Inspect one file', 1001.0),
        )
        connection.commit()

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'state123'
    assert payload['items'][0]['is_auxiliary_cli_session'] is False


def test_get_hermes_sessions_includes_webui_index_sessions(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'webui' / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / '_index.json').write_text(
        json.dumps(
            [
                {
                    'session_id': 'webui123',
                    'title': 'Working Hermes WebUI session',
                    'workspace': str(tmp_path / 'workspace'),
                    'model': 'gpt-5.4',
                    'message_count': 3,
                    'created_at': 1000,
                    'updated_at': 1005,
                    'profile': 'default',
                }
            ]
        ),
        encoding='utf-8',
    )
    (sessions_dir / 'webui123.json').write_text(
        json.dumps(
            {
                'session_id': 'webui123',
                'messages': [
                    {'role': 'user', 'content': 'Continue the WebUI thread'},
                    {'role': 'assistant', 'content': 'ok'},
                ]
            }
        ),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'webui123'
    assert payload['items'][0]['source_tag'] == 'webui'
    assert payload['items'][0]['available_sources'] == ['webui']
    assert payload['items'][0]['profile'] == 'default'
    assert payload['items'][0]['last_user_content'] == 'Continue the WebUI thread'


def test_get_hermes_sessions_reads_named_profile_webui_state_sessions(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    profile_home = hermes_home / 'profiles' / 'work'
    sessions_dir = profile_home / 'webui_state' / 'sessions'
    sessions_dir.mkdir(parents=True)
    (hermes_home / 'active_profile').write_text('work', encoding='utf-8')

    (sessions_dir / '_index.json').write_text(
        json.dumps(
            [
                {
                    'session_id': 'work-webui-123',
                    'title': 'Named profile WebUI session',
                    'workspace': str(tmp_path / 'workspace-work'),
                    'model': 'gpt-5.4',
                    'message_count': 1,
                    'created_at': 2000,
                    'updated_at': 2005,
                    'profile': 'work',
                }
            ]
        ),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()

    assert payload['active_home'] == str(profile_home)
    assert payload['active_profile'] == 'work'
    assert payload['items'][0]['session_id'] == 'work-webui-123'
    assert payload['items'][0]['source_tag'] == 'webui'
    assert payload['items'][0]['profile'] == 'work'


def test_get_hermes_sessions_reads_webui_session_files_missing_from_index(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'webui' / 'sessions'
    sessions_dir.mkdir(parents=True)
    (sessions_dir / '_index.json').write_text('[]', encoding='utf-8')
    (sessions_dir / 'webui-file-only.json').write_text(
        json.dumps(
            {
                'session_id': 'webui-file-only',
                'title': 'File-only WebUI session',
                'model': 'gpt-5.4',
                'session_start': 4000,
                'last_updated': 4005,
                'messages': [
                    {'role': 'user', 'content': 'Open file-only WebUI session'},
                    {'role': 'assistant', 'content': 'ok'},
                ],
            }
        ),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_sessions()

    assert len(payload['items']) == 1
    assert payload['items'][0]['session_id'] == 'webui-file-only'
    assert payload['items'][0]['source_tag'] == 'webui'
    assert payload['items'][0]['last_user_content'] == 'Open file-only WebUI session'


def test_get_hermes_workspaces_reads_default_profile_webui_state(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    state_dir = hermes_home / 'webui'
    workspace_home = tmp_path / 'workspace-home'
    workspace_alt = tmp_path / 'workspace-alt'
    workspace_home.mkdir(parents=True)
    workspace_alt.mkdir(parents=True)
    state_dir.mkdir(parents=True)

    (state_dir / 'workspaces.json').write_text(
        json.dumps(
            [
                {'path': str(workspace_home), 'name': 'default'},
                {'path': str(workspace_alt), 'name': 'Alt'},
            ]
        ),
        encoding='utf-8',
    )
    (state_dir / 'last_workspace.txt').write_text(str(workspace_alt), encoding='utf-8')

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_workspaces()

    assert payload['active_home'] == str(hermes_home)
    assert payload['active_profile'] == 'default'
    assert payload['last_workspace'] == str(workspace_alt.resolve())
    assert payload['items'] == [
        {'path': str(workspace_home.resolve()), 'name': 'Home', 'is_active': False},
        {'path': str(workspace_alt.resolve()), 'name': 'Alt', 'is_active': True},
    ]


def test_get_hermes_workspaces_falls_back_to_profile_config_workspace(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    profile_home = hermes_home / 'profiles' / 'work'
    profile_workspace = tmp_path / 'profile-workspace'
    profile_workspace.mkdir(parents=True)
    profile_home.mkdir(parents=True)
    (hermes_home / 'active_profile').write_text('work', encoding='utf-8')
    (profile_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{profile_workspace}"\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_workspaces()

    assert payload['active_home'] == str(profile_home)
    assert payload['active_profile'] == 'work'
    assert payload['last_workspace'] == str(profile_workspace.resolve())
    assert payload['items'] == [
        {'path': str(profile_workspace.resolve()), 'name': 'Home', 'is_active': True}
    ]


def test_get_hermes_workspaces_keeps_default_workspace_available(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    state_dir = hermes_home / 'webui'
    workspace_default = tmp_path / 'workspace-default'
    workspace_alt = tmp_path / 'workspace-alt'
    workspace_default.mkdir(parents=True)
    workspace_alt.mkdir(parents=True)
    hermes_home.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_default}"\n',
        encoding='utf-8',
    )
    (state_dir / 'workspaces.json').write_text(
        json.dumps([{'path': str(workspace_alt), 'name': 'Alt'}]),
        encoding='utf-8',
    )
    (state_dir / 'last_workspace.txt').write_text(str(workspace_alt), encoding='utf-8')

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    payload = get_hermes_workspaces()

    assert payload['items'] == [
        {'path': str(workspace_default.resolve()), 'name': 'Home', 'is_active': False},
        {'path': str(workspace_alt.resolve()), 'name': 'Alt', 'is_active': True},
    ]


def test_switch_hermes_workspace_updates_last_workspace(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    state_dir = hermes_home / 'webui'
    workspace_default = tmp_path / 'workspace-default'
    workspace_alt = tmp_path / 'workspace-alt'
    workspace_default.mkdir(parents=True)
    workspace_alt.mkdir(parents=True)
    hermes_home.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_default}"\n',
        encoding='utf-8',
    )
    (state_dir / 'workspaces.json').write_text(
        json.dumps([{'path': str(workspace_alt), 'name': 'Alt'}]),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    payload = switch_hermes_workspace(str(workspace_alt))

    assert (state_dir / 'last_workspace.txt').read_text(encoding='utf-8') == str(
        workspace_alt.resolve()
    )
    assert payload['last_workspace'] == str(workspace_alt.resolve())
    assert payload['items'] == [
        {'path': str(workspace_default.resolve()), 'name': 'Home', 'is_active': False},
        {'path': str(workspace_alt.resolve()), 'name': 'Alt', 'is_active': True},
    ]


def test_switch_hermes_workspace_rejects_unknown_or_missing_workspace(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    state_dir = hermes_home / 'webui'
    workspace_default = tmp_path / 'workspace-default'
    workspace_known = tmp_path / 'workspace-known'
    workspace_outside = tmp_path / 'workspace-outside'
    workspace_default.mkdir(parents=True)
    workspace_known.mkdir(parents=True)
    workspace_outside.mkdir(parents=True)
    hermes_home.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_default}"\n',
        encoding='utf-8',
    )
    (state_dir / 'workspaces.json').write_text(
        json.dumps([{'path': str(workspace_known), 'name': 'Known'}]),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    with pytest.raises(ValueError):
        switch_hermes_workspace(str(workspace_outside))

    with pytest.raises(FileNotFoundError):
        switch_hermes_workspace(str(tmp_path / 'workspace-missing'))


def test_browse_hermes_workspace_lists_active_root(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    workspace_root = tmp_path / 'workspace-root'
    workspace_dir = workspace_root / 'notes'
    workspace_file = workspace_root / 'plan.md'
    workspace_root.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    workspace_file.write_text('# plan\n', encoding='utf-8')
    hermes_home.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_root}"\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    payload = browse_hermes_workspace()

    assert payload['root_path'] == str(workspace_root.resolve())
    assert payload['current_path'] == str(workspace_root.resolve())
    assert [entry['name'] for entry in payload['entries']] == ['notes', 'plan.md']
    assert payload['entries'][0]['type'] == 'directory'
    assert payload['entries'][0]['size'] is None
    assert isinstance(payload['entries'][0]['modified'], int)
    assert payload['entries'][1]['type'] == 'file'
    assert payload['entries'][1]['size'] == len('# plan\n')
    assert isinstance(payload['entries'][1]['modified'], int)


def test_browse_hermes_workspace_rejects_paths_outside_root(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    workspace_root = tmp_path / 'workspace-root'
    outside_dir = tmp_path / 'outside'
    workspace_root.mkdir(parents=True)
    outside_dir.mkdir(parents=True)
    hermes_home.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_root}"\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    with pytest.raises(ValueError):
        browse_hermes_workspace(str(outside_dir))


def test_get_hermes_workspace_file_path_restricts_to_active_root(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    workspace_root = tmp_path / 'workspace-root'
    workspace_file = workspace_root / 'plan.md'
    outside_file = tmp_path / 'outside.md'
    workspace_root.mkdir(parents=True)
    workspace_file.write_text('# plan\n', encoding='utf-8')
    outside_file.write_text('nope\n', encoding='utf-8')
    hermes_home.mkdir(parents=True)
    (hermes_home / 'config.yaml').write_text(
        f'terminal:\n  cwd: "{workspace_root}"\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    monkeypatch.delenv('HERMES_HOME', raising=False)

    assert get_hermes_workspace_file_path(str(workspace_file)) == workspace_file.resolve()

    with pytest.raises(ValueError):
        get_hermes_workspace_file_path(str(outside_file))

def test_load_hermes_session_prefers_json_messages(monkeypatch, tmp_path):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    _create_state_db(hermes_home / 'state.db')
    with sqlite3.connect(hermes_home / 'state.db') as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source, model, started_at, message_count, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('abc123', 'cli', 'gpt-5.4', 1000.0, 1, 'DB Title'),
        )
        cursor.execute(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            ('abc123', 'user', 'db fallback message', 1001.0),
        )
        connection.commit()

    (sessions_dir / 'session_abc123.json').write_text(
        """
        {
          "session_id": "abc123",
          "title": "JSON Title",
          "model": "gpt-5.4",
          "session_start": 1000,
          "last_updated": 1005,
          "messages": [
            {"role": "user", "content": "json prompt"},
            {"role": "assistant", "content": "json reply"}
          ]
        }
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))
    session = load_hermes_session('abc123')

    assert session is not None
    assert session['title'] == 'JSON Title'
    assert [message['content'] for message in session['messages']] == ['json prompt', 'json reply']


def test_load_hermes_session_keeps_json_transcript_even_when_state_db_is_fresher(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / '.hermes'
    sessions_dir = hermes_home / 'sessions'
    sessions_dir.mkdir(parents=True)

    _create_state_db(hermes_home / 'state.db')
    with sqlite3.connect(hermes_home / 'state.db') as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source, model, started_at, message_count, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ('abc123', 'cli', 'gpt-5.4', 1000.0, 2, 'DB Title'),
        )
        cursor.executemany(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            [
                ('abc123', 'user', 'state db mirror prompt', 1010.0),
                ('abc123', 'assistant', 'state db mirror reply', 1011.0),
            ],
        )
        connection.commit()

    json_path = sessions_dir / 'session_abc123.json'
    json_path.write_text(
        json.dumps(
            {
                'session_id': 'abc123',
                'title': 'JSON Title',
                'model': 'gpt-5.4',
                'session_start': 1000,
                'last_updated': 1005,
                'messages': [
                    {'role': 'user', 'content': 'canonical json prompt'},
                    {'role': 'assistant', 'content': 'canonical json reply'},
                ],
            }
        ),
        encoding='utf-8',
    )
    os.utime(json_path, (1005, 1005))

    monkeypatch.setenv('HERMES_BASE_HOME', str(hermes_home))

    session = load_hermes_session('abc123')

    assert session is not None
    assert session['title'] == 'JSON Title'
    assert [message['content'] for message in session['messages']] == [
        'canonical json prompt',
        'canonical json reply',
    ]
    assert session['updated_at'] == 1011
    assert set(session['available_sources']) == {'json', 'state_db'}


def test_build_chat_import_payload_preserves_tool_messages():
    payload = build_chat_import_payload(
        {
            'session_id': 'abc123',
            'title': 'Imported session',
            'model': 'gpt-5.4',
            'source_tag': 'cli',
            'active_home': '/tmp/.hermes',
            'profile': 'default',
            'created_at': 1000,
            'updated_at': 1005,
            'messages': [
                {'role': 'user', 'content': 'hello', 'timestamp': 1001},
                {'role': 'tool', 'content': '{"ok": true}', 'tool_name': 'shell', 'timestamp': 1002},
                {'role': 'assistant', 'content': 'done', 'timestamp': 1003},
            ],
        }
    )

    chat = payload['chat']
    assert chat['title'] == 'Imported session'
    assert chat['history']['currentId'] is not None
    assert len(chat['messages']) == 3
    assert chat['messages'][1]['role'] == 'tool'
    assert chat['messages'][1]['content'].startswith('[Tool: shell]')
    assert chat['messages'][1]['model'] == 'gpt-5.4'
    assert chat['messages'][1]['modelName'] == 'Hermes'
    assert chat['messages'][2]['modelName'] == 'Hermes'
    assert chat['hermesSession']['target_id'] == 'local'
    assert chat['hermesSession']['runtime_target_id'] == 'local'
    assert chat['hermesSession']['model'] == 'gpt-5.4'
    assert payload['meta']['hermes']['runtime_target_id'] == 'local'
    assert payload['meta']['hermes']['model'] == 'gpt-5.4'


def test_load_hermes_session_infers_tool_name_from_json_tool_calls(monkeypatch, tmp_path):
    sessions_dir = tmp_path / 'sessions'
    sessions_dir.mkdir(parents=True)

    (sessions_dir / 'session_abc123.json').write_text(
        json.dumps(
            {
                'session_id': 'abc123',
                'title': 'Inferred tool session',
                'model': 'gpt-5.4',
                'messages': [
                    {'role': 'user', 'content': 'run a command'},
                    {
                        'role': 'assistant',
                        'content': '',
                        'tool_calls': [
                            {
                                'id': 'call_1',
                                'call_id': 'call_1',
                                'type': 'function',
                                'function': {
                                    'name': 'terminal',
                                    'arguments': '{"command":"pwd"}',
                                },
                            }
                        ],
                    },
                    {
                        'role': 'tool',
                        'tool_call_id': 'call_1',
                        'content': '{"output":"/tmp","exit_code":0}',
                    },
                    {'role': 'assistant', 'content': '/tmp'},
                ],
            }
        ),
        encoding='utf-8',
    )

    session = load_hermes_session(
        'abc123',
        sessions_payload={
            'active_home': str(tmp_path),
            'active_profile': 'default',
            'items': [{'session_id': 'abc123', 'title': 'Inferred tool session'}],
        },
    )

    assert session is not None
    assert session['messages'][2]['tool_name'] == 'terminal'

    import_payload = build_chat_import_payload(session)
    assert import_payload['chat']['messages'][2]['content'].startswith('[Tool: terminal]')


def test_get_imported_hermes_chat_map_uses_meta_and_chat_payload():
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='chat-meta',
                    user_id='user-1',
                    title='Imported Meta Session',
                    chat={'title': 'Imported Meta Session'},
                    meta={'hermes': {'session_id': 'abc123'}},
                    created_at=1000,
                    updated_at=1005,
                    archived=False,
                    pinned=False,
                ),
                Chat(
                    id='chat-payload',
                    user_id='user-1',
                    title='Imported Payload Session',
                    chat={'title': 'Imported Payload Session', 'hermesSession': {'session_id': 'xyz789'}},
                    meta={},
                    created_at=2000,
                    updated_at=2005,
                    archived=False,
                    pinned=False,
                ),
                Chat(
                    id='other-user',
                    user_id='user-2',
                    title='Other User Session',
                    chat={'title': 'Other User Session'},
                    meta={'hermes': {'session_id': 'abc123'}},
                    created_at=3000,
                    updated_at=3005,
                    archived=False,
                    pinned=False,
                ),
            ]
        )
        db.commit()

        mapping = get_imported_hermes_chat_map(db, 'user-1', ['abc123', 'xyz789'])

    assert mapping == {
        'abc123': {
            'id': 'chat-meta',
            'title': 'Imported Meta Session',
            'created_at': 1000,
            'updated_at': 1005,
            'archived': False,
        },
        'xyz789': {
            'id': 'chat-payload',
            'title': 'Imported Payload Session',
            'created_at': 2000,
            'updated_at': 2005,
            'archived': False,
        },
    }


def test_get_imported_hermes_chat_map_prefers_non_archived_chat():
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='archived-chat',
                    user_id='user-1',
                    title='Archived Import',
                    chat={'title': 'Archived Import'},
                    meta={'hermes': {'session_id': 'abc123'}},
                    created_at=1000,
                    updated_at=5000,
                    archived=True,
                    pinned=False,
                ),
                Chat(
                    id='active-chat',
                    user_id='user-1',
                    title='Active Import',
                    chat={'title': 'Active Import'},
                    meta={'hermes': {'session_id': 'abc123'}},
                    created_at=2000,
                    updated_at=3000,
                    archived=False,
                    pinned=False,
                ),
            ]
        )
        db.commit()

        mapping = get_imported_hermes_chat_map(db, 'user-1', ['abc123'])

    assert mapping['abc123']['id'] == 'active-chat'
    assert mapping['abc123']['archived'] is False


def test_get_imported_hermes_chat_map_returns_archived_when_only_match():
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        archived_import = _build_imported_chat(
            'archived-chat',
            'abc123',
            'Archived import',
            5000,
            archived=True,
        )
        db.add(archived_import)
        db.commit()

        mapping = get_imported_hermes_chat_map(db, 'user-1', ['abc123'])

    assert mapping['abc123']['id'] == archived_import.id
    assert mapping['abc123']['archived'] is True


def test_get_imported_hermes_chat_map_prefers_latest_active_duplicate():
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        first_import = _build_imported_chat('first-chat', 'abc123', 'First import', 1000)
        second_import = _build_imported_chat('second-chat', 'abc123', 'Second import', 2000)
        db.add_all([first_import, second_import])
        db.commit()

        mapping = get_imported_hermes_chat_map(db, 'user-1', ['abc123'])

    assert mapping['abc123']['id'] == second_import.id
    assert mapping['abc123']['title'] == 'Second import'
    assert mapping['abc123']['updated_at'] == second_import.updated_at
    assert mapping['abc123']['id'] != first_import.id


def test_get_imported_hermes_chat_map_uses_chat_payload_session_fallback():
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        legacy_import = _build_imported_chat(
            'legacy-chat',
            'legacy-123',
            'Legacy import',
            1500,
            include_meta=False,
        )
        db.add(legacy_import)
        db.commit()

        mapping = get_imported_hermes_chat_map(db, 'user-1', ['legacy-123'])

    assert mapping['legacy-123']['id'] == legacy_import.id
    assert mapping['legacy-123']['title'] == 'Legacy import'


def test_send_hermes_session_message_requires_message():
    with pytest.raises(ValueError, match='message is required'):
        send_hermes_session_message('session-1', '')


def test_send_hermes_session_message_raises_when_session_missing(monkeypatch):
    monkeypatch.setattr('open_webui.utils.hermes.load_hermes_session', lambda session_id, **kwargs: None)

    with pytest.raises(FileNotFoundError, match='Hermes session not found'):
        send_hermes_session_message('missing-session', 'hello')


def test_build_hermes_message_with_attachments_includes_file_context():
    message = _build_hermes_message_with_attachments(
        'Summarize this file.',
        [
            {
                'name': 'notes.md',
                'content_type': 'text/markdown',
                'size': 42,
                'storage_path': '/tmp/uploads/notes.md',
                'content': '# Notes\nImportant detail.',
            }
        ],
    )

    assert message.startswith('[Attached files]')
    assert 'notes.md' in message
    assert 'Accessible file path: /tmp/uploads/notes.md' in message
    assert '# Notes\nImportant detail.' in message
    assert message.endswith('User request:\nSummarize this file.')


def test_build_hermes_message_with_attachments_caps_metadata_and_file_count():
    long_name = 'a' * 900
    long_url = 'https://example.test/' + ('b' * 3000)
    message = _build_hermes_message_with_attachments(
        '',
        [
            {
                'name': f'{long_name}-{idx}',
                'content_type': 'image/png',
                'url': long_url,
            }
            for idx in range(14)
        ],
    )

    assert 'Only the first 12 attachments were included in this turn.' in message
    assert '13.' not in message
    assert long_name not in message
    assert long_url not in message
    assert 'Image attachment metadata only; no accessible local path was provided.' in message


def test_start_hermes_session_message_process_uses_shared_runner_payload(monkeypatch):
    writes: list[str] = []
    flushes = 0
    captured: dict[str, object] = {}

    class FakeStdin:
        closed = False

        def write(self, value):
            writes.append(value)

        def flush(self):
            nonlocal flushes
            flushes += 1

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None

    context = {
        'runtime': {'active_home': '/tmp/hermes-home'},
        'session_payload': {'messages': [{'role': 'user', 'content': 'seed'}]},
        'normalized_session_id': 'session-123',
        'normalized_message': 'hello',
        'agent_dir': '/tmp/hermes-agent',
        'python_path': '/tmp/hermes-agent/.venv/bin/python',
        'resolved_model': 'gpt-5.4',
        'workspace_path': '/tmp/hermes-workspace',
        'state_db_path': '/tmp/hermes-home/state.db',
    }

    monkeypatch.setattr(
        'open_webui.utils.hermes._resolve_hermes_send_context',
        lambda *args, **kwargs: context,
    )

    def fake_popen(args, stdin, stdout, stderr, text, cwd, env, bufsize):
        captured['args'] = args
        captured['cwd'] = cwd
        captured['env'] = env
        captured['bufsize'] = bufsize
        return FakeProcess()

    monkeypatch.setattr('open_webui.utils.hermes.subprocess.Popen', fake_popen)

    runner = start_hermes_session_message_process('session-123', 'hello', emit_events=True)

    assert runner['context'] == context
    assert captured['args'][0] == '/tmp/hermes-agent/.venv/bin/python'
    assert captured['cwd'] == '/tmp/hermes-agent'
    assert captured['env']['HERMES_HOME'] == '/tmp/hermes-home'
    assert captured['env']['TERMINAL_CWD'] == '/tmp/hermes-workspace'
    assert captured['bufsize'] == 1
    assert flushes == 1
    assert runner['process'].stdin.closed is False
    assert writes[0].endswith('\n')
    payload = json.loads(writes[0].strip())
    assert payload['session_id'] == 'session-123'
    assert payload['message'] == 'hello'
    assert payload['model'] == 'gpt-5.4'
    assert payload['workspace'] == '/tmp/hermes-workspace'
    assert payload['emit_events'] is True


def test_start_hermes_session_message_process_closes_stdin_for_non_stream_send(monkeypatch):
    writes: list[str] = []
    flushes = 0

    class FakeStdin:
        closed = False

        def write(self, value):
            writes.append(value)

        def flush(self):
            nonlocal flushes
            flushes += 1

        def close(self):
            self.closed = True

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None

    context = {
        'runtime': {'active_home': '/tmp/hermes-home'},
        'session_payload': {'messages': [{'role': 'user', 'content': 'seed'}]},
        'normalized_session_id': 'session-123',
        'normalized_message': 'hello',
        'agent_dir': '/tmp/hermes-agent',
        'python_path': '/tmp/hermes-agent/.venv/bin/python',
        'resolved_model': 'gpt-5.4',
        'workspace_path': '/tmp/hermes-workspace',
        'state_db_path': '/tmp/hermes-home/state.db',
    }

    monkeypatch.setattr(
        'open_webui.utils.hermes._resolve_hermes_send_context',
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        'open_webui.utils.hermes.subprocess.Popen',
        lambda *args, **kwargs: FakeProcess(),
    )

    runner = start_hermes_session_message_process('session-123', 'hello', emit_events=False)

    assert flushes == 1
    assert writes[0].endswith('\n')
    assert runner['process'].stdin.closed is True


def test_send_hermes_runner_control_message_writes_json_line_and_flushes():
    writes: list[str] = []
    flushes = 0

    class FakeStdin:
        def write(self, value):
            writes.append(value)

        def flush(self):
            nonlocal flushes
            flushes += 1

    class FakeProcess:
        stdin = FakeStdin()

    send_hermes_runner_control_message(
        FakeProcess(),
        {
            'request_id': 'req-1',
            'action': 'approval.resolve',
            'choice': 'session',
            'resolve_all': False,
        },
    )

    assert flushes == 1
    assert writes == [
        '{"request_id": "req-1", "action": "approval.resolve", "choice": "session", "resolve_all": false}\n'
    ]


def test_send_hermes_session_message_uses_shared_runner_process(monkeypatch):
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return (
                HERMES_RUNNER_RESULT_SENTINEL
                + json.dumps(
                    {
                        'session_id': 'session-123',
                        'answer': 'done',
                        'result': {'usage': {'total_tokens': 5}},
                    }
                ),
                '',
            )

    session_payload = {
        'session_id': 'session-123',
        'title': 'Session 123',
        'model': 'gpt-5.4',
        'messages': [
            {
                'role': 'user',
                'content': 'hello',
                'timestamp': 1000,
            },
            {
                'role': 'assistant',
                'content': 'done',
                'timestamp': 1001,
            },
        ],
        'created_at': 1000,
        'updated_at': 1001,
        'profile': 'default',
        'source_tag': 'open_webui',
        'active_home': '/tmp/hermes-home',
        'available_sources': ['state_db'],
    }

    monkeypatch.setattr(
        'open_webui.utils.hermes.start_hermes_session_message_process',
        lambda *args, **kwargs: {
            'context': {
                'normalized_session_id': 'session-123',
                'session_payload': session_payload,
            },
            'process': FakeProcess(),
        },
    )
    monkeypatch.setattr(
        'open_webui.utils.hermes.load_hermes_session',
        lambda session_id, **kwargs: session_payload,
    )

    result = send_hermes_session_message('session-123', 'hello')

    assert result['session_id'] == 'session-123'
    assert result['answer'] == 'done'
    assert result['result']['usage']['total_tokens'] == 5
    assert result['chat_payload']['chat']['history']['currentId'] is not None


def test_send_hermes_session_message_tolerates_closed_runner_stdin(monkeypatch):
    class FakeStdin:
        closed = True

    class FakeProcess:
        returncode = 0

        def __init__(self):
            self.stdin = FakeStdin()

        def communicate(self, timeout=None):
            if self.stdin is not None:
                raise ValueError('I/O operation on closed file.')
            return (
                HERMES_RUNNER_RESULT_SENTINEL
                + json.dumps(
                    {
                        'session_id': 'session-closed-stdin',
                        'answer': 'OK',
                        'result': {'usage': {'total_tokens': 3}},
                    }
                ),
                '',
            )

    session_payload = {
        'session_id': 'session-closed-stdin',
        'title': 'Closed stdin session',
        'model': 'gpt-5.4',
        'messages': [
            {
                'role': 'user',
                'content': 'hello',
                'timestamp': 1000,
            },
            {
                'role': 'assistant',
                'content': 'OK',
                'timestamp': 1001,
            },
        ],
        'created_at': 1000,
        'updated_at': 1001,
        'profile': 'default',
        'source_tag': 'open_webui',
        'active_home': '/tmp/hermes-home',
        'available_sources': ['state_db'],
    }

    monkeypatch.setattr(
        'open_webui.utils.hermes.start_hermes_session_message_process',
        lambda *args, **kwargs: {
            'context': {
                'normalized_session_id': 'session-closed-stdin',
                'session_payload': session_payload,
            },
            'process': FakeProcess(),
        },
    )
    monkeypatch.setattr(
        'open_webui.utils.hermes.load_hermes_session',
        lambda session_id, **kwargs: session_payload,
    )

    result = send_hermes_session_message('session-closed-stdin', 'hello')

    assert result['session_id'] == 'session-closed-stdin'
    assert result['answer'] == 'OK'
    assert result['result']['usage']['total_tokens'] == 3
