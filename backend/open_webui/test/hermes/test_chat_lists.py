import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from open_webui.models.chats import Chat, Chats, build_chat_list_meta
from open_webui.routers import chats as chats_router


def test_chat_sidebar_lists_preserve_hermes_meta(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='chat-1',
                    user_id='user-1',
                    title='Imported session',
                    chat={
                        'title': 'Imported session',
                        'history': {
                            'currentId': 'assistant-current',
                            'messages': {
                                'user-root': {'id': 'user-root', 'role': 'user', 'content': 'start'},
                                'assistant-root': {
                                    'id': 'assistant-root',
                                    'role': 'assistant',
                                    'content': 'first',
                                    'model': 'openai/gpt-4.1',
                                    'parentId': 'user-root',
                                },
                                'user-current': {
                                    'id': 'user-current',
                                    'role': 'user',
                                    'content': 'continue',
                                    'parentId': 'assistant-root',
                                },
                                'assistant-current': {
                                    'id': 'assistant-current',
                                    'role': 'assistant',
                                    'content': 'second',
                                    'model': 'openai/gpt-5.4',
                                    'parentId': 'user-current',
                                    'statusHistory': [{'type': 'tool'}],
                                },
                                'assistant-off-branch': {
                                    'id': 'assistant-off-branch',
                                    'role': 'assistant',
                                    'content': 'stale branch',
                                    'model': 'openai/gpt-4o-mini',
                                    'parentId': 'assistant-root',
                                },
                            },
                        },
                    },
                    meta={'hermes': {'session_id': 'abc123', 'profile': 'default'}},
                    created_at=1000,
                    updated_at=1005,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
                Chat(
                    id='chat-2',
                    user_id='user-1',
                    title='Pinned imported session',
                    chat={
                        'title': 'Pinned imported session',
                        'history': {
                            'currentId': 'assistant-pinned',
                            'messages': {
                                'user-pinned': {'id': 'user-pinned', 'role': 'user', 'content': 'pin'},
                                'assistant-pinned': {
                                    'id': 'assistant-pinned',
                                    'role': 'assistant',
                                    'content': 'reply',
                                    'model': 'openai/gpt-4.1-mini',
                                    'parentId': 'user-pinned',
                                },
                            },
                        },
                    },
                    meta={'hermes': {'session_id': 'xyz789', 'profile': 'work'}},
                    created_at=2000,
                    updated_at=2005,
                    archived=False,
                    pinned=True,
                    folder_id=None,
                ),
            ]
        )
        db.commit()

        chat_list = Chats.get_chat_title_id_list_by_user_id('user-1', db=db)
        pinned_list = Chats.get_pinned_chats_by_user_id('user-1', db=db)

    assert chat_list[0].meta == {'hermes': {'session_id': 'abc123', 'profile': 'default'}}
    assert chat_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-5.4',
        'assistant_reply_count': 2,
        'operational_turn_count': 1,
    }
    assert pinned_list[0].meta == {'hermes': {'session_id': 'xyz789', 'profile': 'work'}}
    assert pinned_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-4.1-mini',
        'assistant_reply_count': 1,
        'operational_turn_count': 0,
    }


def test_archived_chat_lists_preserve_hermes_meta(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add(
            Chat(
                id='chat-archived',
                user_id='user-1',
                title='Archived imported session',
                chat={
                    'title': 'Archived imported session',
                    'history': {
                        'currentId': 'assistant-archived',
                        'messages': {
                            'user-archived': {'id': 'user-archived', 'role': 'user', 'content': 'archive'},
                            'assistant-archived': {
                                'id': 'assistant-archived',
                                'role': 'assistant',
                                'content': 'archived reply',
                                'model': 'openai/gpt-4.1',
                                'parentId': 'user-archived',
                            },
                        },
                    },
                },
                meta={'hermes': {'session_id': 'arch123', 'profile': 'default'}},
                created_at=3000,
                updated_at=3005,
                archived=True,
                pinned=False,
                folder_id=None,
            )
        )
        db.commit()

        archived_list = Chats.get_archived_chat_list_by_user_id('user-1', db=db)

    assert archived_list[0].meta == {'hermes': {'session_id': 'arch123', 'profile': 'default'}}
    assert archived_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-4.1',
        'assistant_reply_count': 1,
        'operational_turn_count': 0,
    }


def test_shared_chat_lists_preserve_hermes_meta(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add(
            Chat(
                id='chat-shared',
                user_id='user-1',
                title='Shared imported session',
                chat={
                    'title': 'Shared imported session',
                    'history': {
                        'currentId': 'assistant-shared',
                        'messages': {
                            'user-shared': {'id': 'user-shared', 'role': 'user', 'content': 'share'},
                            'assistant-shared': {
                                'id': 'assistant-shared',
                                'role': 'assistant',
                                'content': 'shared reply',
                                'model': 'openai/gpt-5.4',
                                'parentId': 'user-shared',
                                'code_executions': [{'status': 'done'}],
                            },
                        },
                    },
                },
                meta={'hermes': {'session_id': 'share123', 'profile': 'work'}},
                created_at=4000,
                updated_at=4005,
                archived=False,
                pinned=False,
                share_id='share-link-1',
                folder_id=None,
            )
        )
        db.commit()

        shared_list = Chats.get_shared_chat_list_by_user_id('user-1', db=db)

    assert shared_list[0].meta == {'hermes': {'session_id': 'share123', 'profile': 'work'}}
    assert shared_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-5.4',
        'assistant_reply_count': 1,
        'operational_turn_count': 1,
    }


def test_build_chat_list_meta_backfills_hermes_session_without_overwriting_existing_meta():
    assert build_chat_list_meta(
        None,
        {'hermesSession': {'session_id': 'abc123', 'profile': 'work', 'source_tag': 'cli'}},
    ) == {'hermes': {'session_id': 'abc123', 'profile': 'work', 'source_tag': 'cli'}}

    assert build_chat_list_meta(
        {'hermes': {'session_id': 'existing', 'profile': 'default'}},
        {'hermesSession': {'session_id': 'abc123', 'profile': 'work', 'source_tag': 'cli'}},
    ) == {'hermes': {'session_id': 'existing', 'profile': 'default'}}


def test_sidebar_lists_backfill_hermes_meta_from_chat_payload(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='chat-list-backfill',
                    user_id='user-1',
                    title='Imported list session',
                    chat={
                        'title': 'Imported list session',
                        'hermesSession': {'session_id': 'list123', 'profile': 'work', 'source_tag': 'cli'},
                        'history': {
                            'currentId': 'assistant-list',
                            'messages': {
                                'user-list': {'id': 'user-list', 'role': 'user', 'content': 'list'},
                                'assistant-list': {
                                    'id': 'assistant-list',
                                    'role': 'assistant',
                                    'content': 'reply',
                                    'model': 'openai/gpt-5.4',
                                    'parentId': 'user-list',
                                },
                            },
                        },
                    },
                    meta={},
                    created_at=5000,
                    updated_at=5005,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
                Chat(
                    id='chat-pinned-backfill',
                    user_id='user-1',
                    title='Pinned imported session',
                    chat={
                        'title': 'Pinned imported session',
                        'hermesSession': {'session_id': 'pin123', 'profile': 'default', 'source_tag': 'json'},
                        'history': {
                            'currentId': 'assistant-pinned',
                            'messages': {
                                'user-pinned': {'id': 'user-pinned', 'role': 'user', 'content': 'pin'},
                                'assistant-pinned': {
                                    'id': 'assistant-pinned',
                                    'role': 'assistant',
                                    'content': 'reply',
                                    'model': 'openai/gpt-4.1-mini',
                                    'parentId': 'user-pinned',
                                },
                            },
                        },
                    },
                    meta=None,
                    created_at=6000,
                    updated_at=6005,
                    archived=False,
                    pinned=True,
                    folder_id=None,
                ),
            ]
        )
        db.commit()

        chat_list = Chats.get_chat_title_id_list_by_user_id('user-1', db=db)
        pinned_list = Chats.get_pinned_chats_by_user_id('user-1', db=db)

    assert chat_list[0].meta == {'hermes': {'session_id': 'list123', 'profile': 'work', 'source_tag': 'cli'}}
    assert pinned_list[0].meta == {
        'hermes': {'session_id': 'pin123', 'profile': 'default', 'source_tag': 'json'}
    }


def test_main_chat_list_promotes_imported_hermes_chat_by_fresher_session(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='chat-hermes',
                    user_id='user-1',
                    title='Imported Hermes chat',
                    chat={
                        'title': 'Imported Hermes chat',
                        'history': {'currentId': None, 'messages': {}},
                        'hermesSession': {'session_id': 'hermes-1', 'profile': 'default'},
                    },
                    meta={'hermes': {'session_id': 'hermes-1', 'profile': 'default'}},
                    created_at=1000,
                    updated_at=1000,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
                Chat(
                    id='chat-plain',
                    user_id='user-1',
                    title='Plain chat',
                    chat={'title': 'Plain chat', 'history': {'currentId': None, 'messages': {}}},
                    meta={},
                    created_at=2000,
                    updated_at=2000,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
            ]
        )
        db.commit()

        monkeypatch.setattr(
            chats_router,
            'get_hermes_sessions',
            lambda: {
                'active_home': '/tmp/.hermes',
                'active_profile': 'default',
                'items': [
                    {
                        'session_id': 'hermes-1',
                        'title': 'Imported Hermes chat',
                        'updated_at': 3000,
                    }
                ],
            },
        )
        monkeypatch.setattr(
            chats_router,
            'load_hermes_session',
            lambda session_id, sessions_payload=None: {
                'session_id': session_id,
                'title': 'Imported Hermes chat',
                'model': 'openai/gpt-5.4',
                'updated_at': 3000,
                'messages': [
                    {'role': 'user', 'content': 'Continue Hermes'},
                    {'role': 'assistant', 'content': 'Working on it', 'model': 'openai/gpt-5.4'},
                ],
            },
        )

        chat_list = chats_router.get_session_user_chat_list(
            user=SimpleNamespace(id='user-1'),
            db=db,
        )

        refreshed_chat = db.query(Chat).filter_by(id='chat-hermes').first()

    assert [chat.id for chat in chat_list[:2]] == ['chat-hermes', 'chat-plain']
    assert chat_list[0].updated_at == 3000
    assert chat_list[0].meta['hermes']['session_id'] == 'hermes-1'
    assert chat_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-5.4',
        'assistant_reply_count': 1,
        'operational_turn_count': 0,
    }
    assert refreshed_chat.updated_at == 3000


def test_main_chat_list_does_not_promote_imported_chat_without_fresher_hermes_timestamp(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add_all(
            [
                Chat(
                    id='chat-hermes',
                    user_id='user-1',
                    title='Imported Hermes chat',
                    chat={
                        'title': 'Imported Hermes chat',
                        'history': {'currentId': None, 'messages': {}},
                        'hermesSession': {'session_id': 'hermes-1', 'profile': 'default'},
                    },
                    meta={'hermes': {'session_id': 'hermes-1', 'profile': 'default'}},
                    created_at=1000,
                    updated_at=3000,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
                Chat(
                    id='chat-plain',
                    user_id='user-1',
                    title='Plain chat',
                    chat={'title': 'Plain chat', 'history': {'currentId': None, 'messages': {}}},
                    meta={},
                    created_at=3500,
                    updated_at=3500,
                    archived=False,
                    pinned=False,
                    folder_id=None,
                ),
            ]
        )
        db.commit()

        monkeypatch.setattr(
            chats_router,
            'get_hermes_sessions',
            lambda: {
                'active_home': '/tmp/.hermes',
                'active_profile': 'default',
                'items': [
                    {
                        'session_id': 'hermes-1',
                        'title': 'Imported Hermes chat',
                        'updated_at': 2500,
                    }
                ],
            },
        )
        monkeypatch.setattr(
            chats_router,
            'load_hermes_session',
            lambda session_id, sessions_payload=None: (_ for _ in ()).throw(
                AssertionError('stale Hermes timestamps should not trigger a refresh')
            ),
        )

        chat_list = chats_router.get_session_user_chat_list(
            user=SimpleNamespace(id='user-1'),
            db=db,
        )

        refreshed_chat = db.query(Chat).filter_by(id='chat-hermes').first()

    assert [chat.id for chat in chat_list[:2]] == ['chat-plain', 'chat-hermes']
    assert chat_list[1].updated_at == 3000
    assert refreshed_chat.updated_at == 3000


def test_pinned_chat_list_promotes_imported_hermes_chat_by_fresher_session(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Chat.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('open_webui.internal.db.DATABASE_ENABLE_SESSION_SHARING', True)

    with SessionLocal() as db:
        db.add(
            Chat(
                id='chat-pinned-hermes',
                user_id='user-1',
                title='Pinned Hermes chat',
                chat={
                    'title': 'Pinned Hermes chat',
                    'history': {'currentId': None, 'messages': {}},
                    'hermesSession': {'session_id': 'hermes-pinned', 'profile': 'default'},
                },
                meta={'hermes': {'session_id': 'hermes-pinned', 'profile': 'default'}},
                created_at=1000,
                updated_at=1000,
                archived=False,
                pinned=True,
                folder_id=None,
            )
        )
        db.commit()

        monkeypatch.setattr(
            chats_router,
            'get_hermes_sessions',
            lambda: {
                'active_home': '/tmp/.hermes',
                'active_profile': 'default',
                'items': [
                    {
                        'session_id': 'hermes-pinned',
                        'title': 'Pinned Hermes chat',
                        'updated_at': 3200,
                    }
                ],
            },
        )
        monkeypatch.setattr(
            chats_router,
            'load_hermes_session',
            lambda session_id, sessions_payload=None: {
                'session_id': session_id,
                'title': 'Pinned Hermes chat',
                'model': 'openai/gpt-5.4',
                'updated_at': 3200,
                'messages': [
                    {'role': 'user', 'content': 'Refresh pinned'},
                    {'role': 'assistant', 'content': 'Pinned reply', 'model': 'openai/gpt-5.4'},
                ],
            },
        )

        pinned_list = asyncio.run(
            chats_router.get_user_pinned_chats(
                user=SimpleNamespace(id='user-1'),
                db=db,
            )
        )

        refreshed_chat = db.query(Chat).filter_by(id='chat-pinned-hermes').first()

    assert pinned_list[0].id == 'chat-pinned-hermes'
    assert pinned_list[0].updated_at == 3200
    assert pinned_list[0].meta['hermes']['session_id'] == 'hermes-pinned'
    assert pinned_list[0].session_summary == {
        'latest_assistant_model': 'openai/gpt-5.4',
        'assistant_reply_count': 1,
        'operational_turn_count': 0,
    }
    assert refreshed_chat.updated_at == 3200
