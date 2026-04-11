import asyncio
from types import SimpleNamespace

import pytest

from open_webui.models.chats import ChatModel
from open_webui.routers import hermes as hermes_router


def _chat_model(chat_id: str, title: str, session_id: str, *, archived: bool = False) -> ChatModel:
    return ChatModel(
        id=chat_id,
        user_id='user-1',
        title=title,
        chat={
            'title': title,
            'history': {'messages': {}, 'currentId': None},
            'hermesSession': {'session_id': session_id},
        },
        meta={'hermes': {'session_id': session_id}},
        created_at=1000,
        updated_at=1005,
        archived=archived,
        pinned=False,
        folder_id=None,
    )


def test_list_sessions_marks_existing_imports(monkeypatch):
    monkeypatch.setattr(
        hermes_router,
        'get_hermes_sessions',
        lambda *args, **kwargs: {
            'active_home': '/tmp/.hermes',
            'active_profile': 'default',
            'items': [
                {
                    'session_id': 'abc123',
                    'title': 'Imported session',
                    'message_count': 3,
                    'available_sources': ['json'],
                    'is_auxiliary_cli_session': False,
                },
                {
                    'session_id': 'xyz789',
                    'title': 'Fresh session',
                    'message_count': 1,
                    'available_sources': ['state_db'],
                    'is_auxiliary_cli_session': True,
                },
            ],
        },
    )
    monkeypatch.setattr(
        hermes_router,
        'get_imported_hermes_chat_map',
        lambda db, user_id, session_ids: {
            'abc123': {
                'id': 'chat-1',
                'title': 'Imported session',
                'created_at': 1000,
                'updated_at': 1005,
                'archived': False,
            }
        },
    )

    response = asyncio.run(
        hermes_router.list_sessions(
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.items[0].imported_chat_id == 'chat-1'
    assert response.items[0].imported_chat_archived is False
    assert response.items[0].is_auxiliary_cli_session is False
    assert response.items[1].imported_chat_id is None
    assert response.items[1].is_auxiliary_cli_session is True


def test_resolve_storage_path_requires_resolvable_local_file(monkeypatch, tmp_path):
    missing_path = tmp_path / 'missing.txt'
    existing_path = tmp_path / 'existing.txt'
    existing_path.write_text('ok')

    monkeypatch.setattr(
        hermes_router.Storage,
        'get_file',
        lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
    )

    assert hermes_router._resolve_storage_path(str(missing_path)) is None
    assert hermes_router._resolve_storage_path(str(existing_path)) == str(existing_path.resolve())


def test_import_session_returns_existing_chat_when_already_imported(monkeypatch):
    existing_chat = _chat_model('chat-1', 'Imported session', 'abc123')
    refresh_calls = []

    monkeypatch.setattr(
        hermes_router,
        'get_imported_hermes_chat_map',
        lambda db, user_id, session_ids: {'abc123': {'id': 'chat-1', 'archived': False}},
    )
    monkeypatch.setattr(
        hermes_router.Chats,
        'get_chat_by_id_and_user_id',
        lambda chat_id, user_id, db=None: (_ for _ in ()).throw(
            AssertionError('should not fall back to stale existing chat when refresh succeeds')
        ),
    )
    monkeypatch.setattr(
        hermes_router,
        'load_hermes_session',
        lambda session_id, **kwargs: {
            'session_id': session_id,
            'title': 'Imported session',
            'updated_at': 2000,
            'messages': [{'role': 'user', 'content': 'hello'}],
        },
    )
    monkeypatch.setattr(
        hermes_router,
        '_refresh_existing_imported_chat',
        lambda db, chat_id, user_id, session_payload: (
            refresh_calls.append((chat_id, user_id, session_payload['session_id'])) or existing_chat
        ),
    )
    monkeypatch.setattr(
        hermes_router.Chats,
        'import_chats',
        lambda user_id, chat_import_forms, db=None: (_ for _ in ()).throw(
            AssertionError('should not import an already imported session')
        ),
    )

    response = asyncio.run(
        hermes_router.import_session(
            hermes_router.HermesImportRequest(session_id='abc123'),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.session_id == 'abc123'
    assert response.already_imported is True
    assert response.chat.id == 'chat-1'
    assert refresh_calls == [('chat-1', 'user-1', 'abc123')]


def test_import_session_returns_existing_archived_chat_when_already_imported(monkeypatch):
    existing_chat = _chat_model('chat-archived', 'Archived imported session', 'abc123', archived=True)

    monkeypatch.setattr(
        hermes_router,
        'get_imported_hermes_chat_map',
        lambda db, user_id, session_ids: {'abc123': {'id': 'chat-archived', 'archived': True}},
    )
    monkeypatch.setattr(
        hermes_router.Chats,
        'get_chat_by_id_and_user_id',
        lambda chat_id, user_id, db=None: existing_chat,
    )
    monkeypatch.setattr(
        hermes_router,
        'load_hermes_session',
        lambda session_id, **kwargs: None,
    )
    monkeypatch.setattr(
        hermes_router,
        '_refresh_existing_imported_chat',
        lambda db, chat_id, user_id, session_payload: (_ for _ in ()).throw(
            AssertionError('should not refresh when no live Hermes payload is available')
        ),
    )
    monkeypatch.setattr(
        hermes_router.Chats,
        'import_chats',
        lambda user_id, chat_import_forms, db=None: (_ for _ in ()).throw(
            AssertionError('should not import an already imported session')
        ),
    )

    response = asyncio.run(
        hermes_router.import_session(
            hermes_router.HermesImportRequest(session_id='abc123'),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.session_id == 'abc123'
    assert response.already_imported is True
    assert response.chat.id == 'chat-archived'
    assert response.chat.archived is True


def test_import_session_imports_when_no_existing_mapping(monkeypatch):
    imported_chat = _chat_model('chat-2', 'Fresh import', 'xyz789')

    monkeypatch.setattr(
        hermes_router,
        'get_imported_hermes_chat_map',
        lambda db, user_id, session_ids: {},
    )
    monkeypatch.setattr(
        hermes_router,
        'load_hermes_session',
        lambda session_id, **kwargs: {
            'session_id': session_id,
            'title': 'Fresh import',
            'messages': [{'role': 'user', 'content': 'hello'}],
        },
    )
    monkeypatch.setattr(
        hermes_router,
        'build_chat_import_payload',
        lambda session: {'chat': {'title': session['title'], 'history': {'messages': {}, 'currentId': None}}},
    )
    monkeypatch.setattr(
        hermes_router.Chats,
        'import_chats',
        lambda user_id, chat_import_forms, db=None: [imported_chat],
    )

    response = asyncio.run(
        hermes_router.import_session(
            hermes_router.HermesImportRequest(session_id='xyz789'),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.session_id == 'xyz789'
    assert response.already_imported is False
    assert response.chat.id == 'chat-2'


def test_refresh_existing_imported_chat_preserves_local_fields_and_syncs_hermes_timestamp(monkeypatch):
    existing_chat = _chat_model('chat-refresh', 'Imported session', 'abc123')
    existing_chat.chat['files'] = [{'id': 'file-1'}]
    existing_chat.chat['params'] = {'temperature': 0.2}
    existing_chat.chat['tags'] = ['keep-local']
    existing_chat.meta = {'tags': ['keep-meta'], 'hermes': {'session_id': 'abc123', 'profile': 'default'}}
    existing_chat.updated_at = 1500

    monkeypatch.setattr(
        hermes_router,
        'build_chat_import_payload',
        lambda session: {
            'chat': {
                'title': 'Refreshed title',
                'models': ['openai/gpt-5.4'],
                'history': {'messages': {'assistant-1': {'id': 'assistant-1'}}, 'currentId': 'assistant-1'},
                'messages': [{'id': 'assistant-1', 'role': 'assistant'}],
                'params': {},
                'files': [],
                'tags': [],
                'hermesSession': {'session_id': session['session_id'], 'profile': 'work'},
            },
            'meta': {'hermes': {'session_id': session['session_id'], 'profile': 'work'}},
        },
    )

    class _FakeQuery:
        def __init__(self, item):
            self.item = item

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return self.item

    class _FakeDB:
        def __init__(self, item):
            self.item = item
            self.committed = False
            self.refreshed = False

        def query(self, model):
            return _FakeQuery(self.item)

        def commit(self):
            self.committed = True

        def refresh(self, item):
            self.refreshed = True

    fake_db = _FakeDB(existing_chat)

    refreshed_chat = hermes_router._refresh_existing_imported_chat(
        fake_db,
        'chat-refresh',
        'user-1',
        {'session_id': 'abc123', 'updated_at': 2000, 'messages': [{'role': 'user', 'content': 'hello'}]},
    )

    assert refreshed_chat is not None
    assert refreshed_chat.title == 'Refreshed title'
    assert refreshed_chat.updated_at == 2000
    assert refreshed_chat.chat['files'] == [{'id': 'file-1'}]
    assert refreshed_chat.chat['params'] == {'temperature': 0.2}
    assert refreshed_chat.chat['tags'] == ['keep-local']
    assert refreshed_chat.meta['tags'] == ['keep-meta']
    assert refreshed_chat.meta['hermes'] == {'session_id': 'abc123', 'profile': 'work'}
    assert fake_db.committed is True
    assert fake_db.refreshed is True


def test_list_workspaces_returns_profile_aware_workspace_context(monkeypatch):
    monkeypatch.setattr(
        hermes_router,
        'get_hermes_workspaces',
        lambda: {
            'active_home': '/tmp/.hermes',
            'active_profile': 'default',
            'last_workspace': '/tmp/workspace-alt',
            'items': [
                {'path': '/tmp/workspace-home', 'name': 'Home', 'is_active': False},
                {'path': '/tmp/workspace-alt', 'name': 'Alt', 'is_active': True},
            ],
        },
    )

    response = asyncio.run(
        hermes_router.list_workspaces(
            user=SimpleNamespace(id='user-1'),
        )
    )

    assert response.active_home == '/tmp/.hermes'
    assert response.active_profile == 'default'
    assert response.last_workspace == '/tmp/workspace-alt'
    assert response.items[0].name == 'Home'
    assert response.items[1].is_active is True


def test_list_profiles_returns_profile_context(monkeypatch):
    monkeypatch.setattr(
        hermes_router,
        'get_hermes_profiles',
        lambda: {
            'active_home': '/tmp/.hermes',
            'active_profile': 'default',
            'items': [
                {
                    'name': 'default',
                    'path': '/tmp/.hermes',
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
                    'skill_count': 90,
                }
            ],
        },
    )

    response = asyncio.run(
        hermes_router.list_profiles(
            user=SimpleNamespace(id='user-1'),
        )
    )

    assert response.active_home == '/tmp/.hermes'
    assert response.active_profile == 'default'
    assert response.items[0].name == 'default'
    assert response.items[0].is_default is True
    assert response.items[0].is_active is True
    assert response.items[0].model == 'gpt-5.4'
    assert response.items[0].has_user_profile is True
    assert response.items[0].skill_count == 90


def test_run_stream_worker_forwards_approval_events_and_final_done(monkeypatch):
    events = []

    class FakeReadable:
        def __init__(self, lines):
            self.lines = list(lines)

        def readline(self):
            if self.lines:
                return self.lines.pop(0)
            return ''

    class FakeStdin:
        closed = False

        def close(self):
            self.closed = True

    class FakeSelector:
        def __init__(self):
            self.items = {}

        def register(self, fileobj, _events, data=None):
            self.items[fileobj] = SimpleNamespace(fileobj=fileobj, data=data)

        def unregister(self, fileobj):
            self.items.pop(fileobj, None)

        def get_map(self):
            return self.items

        def select(self, timeout=None):
            return [(key, None) for key in list(self.items.values())]

        def close(self):
            return None

    class FakeProcess:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeReadable(['approval-pending\n', 'approval-resolved\n', 'runner-result\n'])
            self.stderr = FakeReadable([])

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            raise AssertionError('stream worker should not terminate a healthy process')

        def kill(self):
            raise AssertionError('stream worker should not kill a healthy process')

    monkeypatch.setattr(hermes_router.selectors, 'DefaultSelector', FakeSelector)
    monkeypatch.setattr(
        hermes_router,
        '_parse_hermes_runner_event',
        lambda line: {
            'approval-pending': {
                'event': 'approval.pending',
                'data': {'command': 'rm -rf ./tmp', 'description': 'Dangerous command'},
            },
            'approval-resolved': {
                'event': 'approval.resolved',
                'data': {'request_id': 'req-1', 'choice': 'session'},
            },
        }.get(line),
    )
    monkeypatch.setattr(
        hermes_router,
        '_parse_hermes_runner_result',
        lambda stdout: {'session_id': 'session-123', 'answer': 'done', 'result': {'usage': {'total_tokens': 5}}},
    )
    monkeypatch.setattr(
        hermes_router,
        '_build_hermes_session_message_result',
        lambda context, runner_result: {
            'session_id': 'session-123',
            'answer': 'done',
            'chat_payload': {'chat': {'history': {'messages': {}, 'currentId': None}}, 'meta': {'hermes': True}},
            'result': runner_result['result'],
        },
    )

    state = hermes_router.HermesSessionStreamState(stream_id='stream-1', session_id='session-123')
    process = FakeProcess()
    context = {'normalized_session_id': 'session-123'}

    hermes_router._run_stream_worker(state, context, process)

    while not state.queue.empty():
        events.append(state.queue.get_nowait())

    assert [item['event'] for item in events] == ['approval.pending', 'approval.resolved', 'done']
    assert state.status == 'completed'
    assert state.done is True
    assert state.approval_pending is None
    assert state.result['session_id'] == 'session-123'
    assert process.stdin.closed is True


def test_submit_session_approval_sends_approval_control_payload(monkeypatch):
    stream_id = 'stream-approval'
    state = hermes_router.HermesSessionStreamState(
        stream_id=stream_id,
        session_id='session-123',
        status='waiting_approval',
        process=SimpleNamespace(stdin=object()),
    )
    state.approval_pending = {'command': 'rm -rf ./tmp', 'description': 'Dangerous command'}

    captured = {}

    monkeypatch.setattr(
        hermes_router,
        'send_hermes_runner_control_message',
        lambda process, payload: (
            captured.update({'payload': payload}),
            hermes_router._apply_stream_runtime_event(
                state,
                'approval.resolved',
                {'request_id': payload['request_id'], 'choice': payload['choice']},
            ),
        ),
    )

    with hermes_router.HERMES_SESSION_STREAMS_LOCK:
        hermes_router.HERMES_SESSION_STREAMS[stream_id] = state

    try:
        response = asyncio.run(
            hermes_router.submit_session_approval(
                hermes_router.HermesSessionApprovalRequest(
                    stream_id=stream_id,
                    choice='session',
                ),
                user=SimpleNamespace(id='user-1'),
            )
        )
    finally:
        with hermes_router.HERMES_SESSION_STREAMS_LOCK:
            hermes_router.HERMES_SESSION_STREAMS.pop(stream_id, None)

    assert captured['payload']['action'] == 'approval.resolve'
    assert captured['payload']['choice'] == 'session'
    assert captured['payload']['resolve_all'] is False
    assert captured['payload']['request_id'] == response.request_id
    assert response.stream_id == stream_id
    assert response.session_id == 'session-123'
    assert response.status == 'running'
    assert state.approval_pending is None


def test_submit_session_approval_rejects_inactive_stream():
    state = hermes_router.HermesSessionStreamState(
        stream_id='stream-inactive',
        session_id='session-123',
        status='completed',
        done=True,
    )

    with hermes_router.HERMES_SESSION_STREAMS_LOCK:
        hermes_router.HERMES_SESSION_STREAMS[state.stream_id] = state

    try:
        with pytest.raises(hermes_router.HTTPException) as exc_info:
            asyncio.run(
                hermes_router.submit_session_approval(
                    hermes_router.HermesSessionApprovalRequest(
                        stream_id=state.stream_id,
                        choice='session',
                    ),
                    user=SimpleNamespace(id='user-1'),
                )
            )
    finally:
        with hermes_router.HERMES_SESSION_STREAMS_LOCK:
            hermes_router.HERMES_SESSION_STREAMS.pop(state.stream_id, None)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == 'Hermes stream is already complete.'


def test_get_session_stream_status_includes_result_and_pending_approval():
    stream_id = 'stream-status'
    state = hermes_router.HermesSessionStreamState(
        stream_id=stream_id,
        session_id='session-123',
        target_id='local',
        status='waiting_approval',
        done=False,
    )
    state.result = {
        'session_id': 'session-123',
        'answer': 'done',
        'chat': {'history': {'messages': {}, 'currentId': None}},
        'meta': {'hermes': True},
        'result': {'usage': {'total_tokens': 7}},
    }
    state.approval_pending = {
        'command': 'rm -rf ./tmp',
        'description': 'Dangerous command',
    }

    with hermes_router.HERMES_SESSION_STREAMS_LOCK:
        hermes_router.HERMES_SESSION_STREAMS[stream_id] = state

    try:
        response = asyncio.run(
            hermes_router.get_session_stream_status(
                stream_id=stream_id,
                user=SimpleNamespace(id='user-1'),
            )
        )
    finally:
        with hermes_router.HERMES_SESSION_STREAMS_LOCK:
            hermes_router.HERMES_SESSION_STREAMS.pop(stream_id, None)

    assert response.stream_id == stream_id
    assert response.target_id == 'local'
    assert response.session_id == 'session-123'
    assert response.status == 'waiting_approval'
    assert response.result['session_id'] == 'session-123'
    assert response.approval_pending['command'] == 'rm -rf ./tmp'


def test_start_session_stream_reuses_existing_stream_for_same_client_request_id(monkeypatch):
    stream_id = 'stream-existing'
    state = hermes_router.HermesSessionStreamState(
        stream_id=stream_id,
        session_id='session-123',
        target_id='local',
        client_request_id='request-1',
        status='running',
    )

    with hermes_router.HERMES_SESSION_STREAMS_LOCK:
        hermes_router.HERMES_SESSION_STREAMS[stream_id] = state
        hermes_router.HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID['local:request-1'] = stream_id

    start_calls = []
    monkeypatch.setattr(
        hermes_router,
        'start_hermes_session_message_process',
        lambda *args, **kwargs: start_calls.append((args, kwargs)),
    )

    try:
        response = asyncio.run(
            hermes_router.start_session_stream(
                hermes_router.HermesSessionMessageRequest(
                    session_id=None,
                    message='hello',
                    client_request_id='request-1',
                ),
                user=SimpleNamespace(id='user-1'),
            )
        )
    finally:
        with hermes_router.HERMES_SESSION_STREAMS_LOCK:
            hermes_router.HERMES_SESSION_STREAMS.pop(stream_id, None)
            hermes_router.HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop('local:request-1', None)

    assert response.stream_id == stream_id
    assert response.target_id == 'local'
    assert response.session_id == 'session-123'
    assert response.status == 'running'
    assert start_calls == []


def test_start_session_stream_does_not_reuse_existing_stream_for_different_target(monkeypatch):
    stream_id = 'stream-existing-remote'
    state = hermes_router.HermesSessionStreamState(
        stream_id=stream_id,
        session_id='session-remote',
        target_id='remote',
        client_request_id='request-1',
        status='running',
    )

    with hermes_router.HERMES_SESSION_STREAMS_LOCK:
        hermes_router.HERMES_SESSION_STREAMS[stream_id] = state
        hermes_router.HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID['remote:request-1'] = stream_id

    monkeypatch.setattr(
        hermes_router,
        'start_hermes_session_message_process',
        lambda *args, **kwargs: {
            'context': {'normalized_session_id': 'session-local', 'target_id': 'local'},
            'process': object(),
        },
    )
    monkeypatch.setattr(
        hermes_router.threading,
        'Thread',
        lambda *args, **kwargs: SimpleNamespace(start=lambda: None),
    )

    try:
        response = asyncio.run(
            hermes_router.start_session_stream(
                hermes_router.HermesSessionMessageRequest(
                    session_id=None,
                    message='hello',
                    client_request_id='request-1',
                    target_id='local',
                ),
                user=SimpleNamespace(id='user-1'),
            )
        )
    finally:
        with hermes_router.HERMES_SESSION_STREAMS_LOCK:
            hermes_router.HERMES_SESSION_STREAMS.pop(stream_id, None)
            hermes_router.HERMES_SESSION_STREAMS.pop(response.stream_id, None)
            hermes_router.HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop('remote:request-1', None)
            hermes_router.HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop('local:request-1', None)

    assert response.stream_id != stream_id
    assert response.target_id == 'local'
    assert response.session_id == 'session-local'
