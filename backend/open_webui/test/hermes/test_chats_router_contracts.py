import asyncio
from types import SimpleNamespace

from open_webui.models.chats import ChatModel
from open_webui.routers import chats as chats_router


def test_folder_chat_list_preserves_hermes_meta(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chats_by_folder_id_and_user_id',
        lambda folder_id, user_id, skip=0, limit=10, db=None: [
            ChatModel(
                id='chat-1',
                user_id=user_id,
                title='Imported folder session',
                chat={
                    'title': 'Imported folder session',
                    'history': {
                        'currentId': 'assistant-1',
                        'messages': {
                            'user-1': {'id': 'user-1', 'role': 'user', 'content': 'folder'},
                            'assistant-1': {
                                'id': 'assistant-1',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                                'parentId': 'user-1',
                            },
                        },
                    },
                },
                meta={'hermes': {'session_id': 'abc123', 'profile': 'default'}},
                created_at=1000,
                updated_at=1005,
                archived=False,
                pinned=False,
                folder_id=folder_id,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_chat_list_by_folder_id(
            'folder-1',
            page=1,
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Imported folder session',
            'id': 'chat-1',
            'updated_at': 1005,
            'created_at': 1000,
            'meta': {'hermes': {'session_id': 'abc123', 'profile': 'default'}},
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_admin_chat_list_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(chats_router, 'ENABLE_ADMIN_CHAT_ACCESS', True)
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_list_by_user_id',
        lambda user_id, include_archived=True, filter=None, skip=0, limit=60, db=None: [
            ChatModel(
                id='chat-admin-1',
                user_id=user_id,
                title='Admin legacy Hermes chat',
                chat={
                    'title': 'Admin legacy Hermes chat',
                    'hermesSession': {
                        'session_id': 'admin123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {
                        'currentId': 'assistant-admin-1',
                        'messages': {
                            'assistant-admin-1': {
                                'id': 'assistant-admin-1',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                            }
                        },
                    },
                },
                meta={},
                created_at=1500,
                updated_at=1505,
                archived=False,
                pinned=False,
                folder_id=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_user_chat_list_by_user_id(
            'user-1',
            page=1,
            user=SimpleNamespace(id='admin-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Admin legacy Hermes chat',
            'id': 'chat-admin-1',
            'updated_at': 1505,
            'created_at': 1500,
            'meta': {
                'hermes': {'session_id': 'admin123', 'profile': 'work', 'source_tag': 'cli'}
            },
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_folder_chat_list_normalizes_empty_meta(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chats_by_folder_id_and_user_id',
        lambda folder_id, user_id, skip=0, limit=10, db=None: [
            SimpleNamespace(
                id='chat-2',
                title='Regular folder chat',
                updated_at=2005,
                created_at=2000,
                chat={'title': 'Regular folder chat', 'history': {'messages': {}, 'currentId': None}},
                meta=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_chat_list_by_folder_id(
            'folder-1',
            page=1,
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Regular folder chat',
            'id': 'chat-2',
            'updated_at': 2005,
            'created_at': 2000,
            'meta': {},
            'session_summary': None,
        }
    ]


def test_folder_chat_list_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chats_by_folder_id_and_user_id',
        lambda folder_id, user_id, skip=0, limit=10, db=None: [
            SimpleNamespace(
                id='chat-3',
                title='Imported folder session',
                updated_at=3005,
                created_at=3000,
                chat={
                    'title': 'Imported folder session',
                    'hermesSession': {
                        'session_id': 'folder123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {
                        'currentId': 'assistant-3',
                        'messages': {
                            'user-3': {'id': 'user-3', 'role': 'user', 'content': 'folder'},
                            'assistant-3': {
                                'id': 'assistant-3',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                                'parentId': 'user-3',
                            },
                        },
                    },
                },
                meta=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_chat_list_by_folder_id(
            'folder-1',
            page=1,
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Imported folder session',
            'id': 'chat-3',
            'updated_at': 3005,
            'created_at': 3000,
            'meta': {
                'hermes': {'session_id': 'folder123', 'profile': 'work', 'source_tag': 'cli'}
            },
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_folder_chat_response_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chats_by_folder_ids_and_user_id',
        lambda folder_ids, user_id, db=None: [
            ChatModel(
                id='chat-folder-raw',
                user_id=user_id,
                title='Folder raw Hermes chat',
                chat={
                    'title': 'Folder raw Hermes chat',
                    'hermesSession': {
                        'session_id': 'folder-raw-123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {'messages': {}, 'currentId': None},
                },
                meta={},
                created_at=3500,
                updated_at=3505,
                archived=False,
                pinned=False,
                folder_id=folder_ids[0],
            )
        ],
    )
    monkeypatch.setattr(
        chats_router.Folders,
        'get_children_folders_by_id_and_user_id',
        lambda folder_id, user_id, db=None: [],
    )

    response = asyncio.run(
        chats_router.get_chats_by_folder_id(
            'folder-raw',
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert len(response) == 1
    assert response[0].meta == {
        'hermes': {'session_id': 'folder-raw-123', 'profile': 'work', 'source_tag': 'cli'}
    }


def test_admin_chat_list_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(chats_router, 'ENABLE_ADMIN_CHAT_ACCESS', True)
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_list_by_user_id',
        lambda user_id, include_archived=False, filter=None, skip=0, limit=50, db=None: [
            ChatModel(
                id='chat-admin',
                user_id=user_id,
                title='Admin list Hermes chat',
                chat={
                    'title': 'Admin list Hermes chat',
                    'hermesSession': {
                        'session_id': 'admin123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {
                        'currentId': 'assistant-admin',
                        'messages': {
                            'assistant-admin': {
                                'id': 'assistant-admin',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                            }
                        },
                    },
                },
                meta={},
                created_at=3600,
                updated_at=3605,
                archived=False,
                pinned=False,
                folder_id=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_user_chat_list_by_user_id(
            'user-1',
            page=1,
            user=SimpleNamespace(id='admin-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Admin list Hermes chat',
            'id': 'chat-admin',
            'updated_at': 3605,
            'created_at': 3600,
            'meta': {
                'hermes': {'session_id': 'admin123', 'profile': 'work', 'source_tag': 'cli'}
            },
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_tag_chat_list_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_list_by_user_id_and_tag_name',
        lambda user_id, tag_name, skip=0, limit=50, db=None: [
            ChatModel(
                id='chat-tag',
                user_id=user_id,
                title='Tagged Hermes chat',
                chat={
                    'title': 'Tagged Hermes chat',
                    'hermesSession': {
                        'session_id': 'tag123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {
                        'currentId': 'assistant-tag',
                        'messages': {
                            'assistant-tag': {
                                'id': 'assistant-tag',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                            }
                        },
                    },
                },
                meta={},
                created_at=3700,
                updated_at=3705,
                archived=False,
                pinned=False,
                folder_id=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_user_chat_list_by_tag_name(
            chats_router.TagFilterForm(name='hermes', skip=0, limit=50),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Tagged Hermes chat',
            'id': 'chat-tag',
            'updated_at': 3705,
            'created_at': 3700,
            'meta': {'hermes': {'session_id': 'tag123', 'profile': 'work', 'source_tag': 'cli'}},
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_get_chat_by_id_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_by_id_and_user_id',
        lambda chat_id, user_id, db=None: ChatModel(
            id=chat_id,
            user_id=user_id,
            title='Legacy Hermes chat',
            chat={
                'title': 'Legacy Hermes chat',
                'hermesSession': {
                    'session_id': 'direct123',
                    'profile': 'work',
                    'source_tag': 'cli',
                },
                'history': {'messages': {}, 'currentId': None},
            },
            meta={},
            created_at=4000,
            updated_at=4005,
            archived=False,
            pinned=False,
            folder_id=None,
        ),
    )

    response = asyncio.run(
        chats_router.get_chat_by_id(
            'chat-legacy',
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.meta == {
        'hermes': {'session_id': 'direct123', 'profile': 'work', 'source_tag': 'cli'}
    }


def test_update_chat_by_id_preserves_and_backfills_legacy_hermes_meta(monkeypatch):
    existing_chat = ChatModel(
        id='chat-legacy',
        user_id='user-1',
        title='Legacy Hermes chat',
        chat={
            'title': 'Legacy Hermes chat',
            'hermesSession': {
                'session_id': 'direct123',
                'profile': 'work',
                'source_tag': 'cli',
            },
            'history': {'messages': {}, 'currentId': None},
        },
        meta={},
        created_at=5000,
        updated_at=5005,
        archived=False,
        pinned=False,
        folder_id=None,
    )

    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_by_id_and_user_id',
        lambda chat_id, user_id, db=None: existing_chat,
    )

    def _update_chat_by_id(chat_id, updated_chat, db=None):
        assert updated_chat['hermesSession'] == existing_chat.chat['hermesSession']

        return ChatModel(
            id=chat_id,
            user_id='user-1',
            title=updated_chat['title'],
            chat=updated_chat,
            meta={},
            created_at=5000,
            updated_at=5010,
            archived=False,
            pinned=False,
            folder_id=None,
        )

    monkeypatch.setattr(chats_router.Chats, 'update_chat_by_id', _update_chat_by_id)

    response = asyncio.run(
        chats_router.update_chat_by_id(
            'chat-legacy',
            chats_router.ChatForm(
                chat={
                    'title': 'Legacy Hermes chat updated',
                    'history': {'messages': {'assistant-1': {'id': 'assistant-1', 'role': 'assistant'}}, 'currentId': 'assistant-1'},
                }
            ),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.chat['hermesSession'] == {
        'session_id': 'direct123',
        'profile': 'work',
        'source_tag': 'cli',
    }
    assert response.meta == {
        'hermes': {'session_id': 'direct123', 'profile': 'work', 'source_tag': 'cli'}
    }


def test_pin_chat_by_id_backfills_legacy_hermes_meta(monkeypatch):
    pinned_chat = ChatModel(
        id='chat-pin',
        user_id='user-1',
        title='Pinned Hermes chat',
        chat={
            'title': 'Pinned Hermes chat',
            'hermesSession': {
                'session_id': 'pin123',
                'profile': 'work',
                'source_tag': 'cli',
            },
            'history': {'messages': {}, 'currentId': None},
        },
        meta={},
        created_at=6000,
        updated_at=6005,
        archived=False,
        pinned=True,
        folder_id=None,
    )

    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_by_id_and_user_id',
        lambda chat_id, user_id, db=None: pinned_chat,
    )
    monkeypatch.setattr(
        chats_router.Chats,
        'toggle_chat_pinned_by_id',
        lambda chat_id, db=None: pinned_chat,
    )

    response = asyncio.run(
        chats_router.pin_chat_by_id(
            'chat-pin',
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.meta == {
        'hermes': {'session_id': 'pin123', 'profile': 'work', 'source_tag': 'cli'}
    }


def test_tag_chat_list_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'get_chat_list_by_user_id_and_tag_name',
        lambda user_id, tag_name, skip=0, limit=50, db=None: [
            ChatModel(
                id='chat-tag-1',
                user_id=user_id,
                title='Tagged Hermes chat',
                chat={
                    'title': 'Tagged Hermes chat',
                    'hermesSession': {
                        'session_id': 'tag123',
                        'profile': 'work',
                        'source_tag': 'cli',
                    },
                    'history': {
                        'currentId': 'assistant-tag-1',
                        'messages': {
                            'assistant-tag-1': {
                                'id': 'assistant-tag-1',
                                'role': 'assistant',
                                'content': 'reply',
                                'model': 'openai/gpt-5.4',
                            }
                        },
                    },
                },
                meta={},
                created_at=6500,
                updated_at=6505,
                archived=False,
                pinned=False,
                folder_id=None,
            )
        ],
    )

    response = asyncio.run(
        chats_router.get_user_chat_list_by_tag_name(
            chats_router.TagFilterForm(name='project', skip=0, limit=50),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response == [
        {
            'title': 'Tagged Hermes chat',
            'id': 'chat-tag-1',
            'updated_at': 6505,
            'created_at': 6500,
            'meta': {
                'hermes': {'session_id': 'tag123', 'profile': 'work', 'source_tag': 'cli'}
            },
            'session_summary': {
                'latest_assistant_model': 'openai/gpt-5.4',
                'assistant_reply_count': 1,
                'operational_turn_count': 0,
            },
        }
    ]


def test_create_new_chat_backfills_hermes_meta_from_chat_payload(monkeypatch):
    monkeypatch.setattr(
        chats_router.Chats,
        'insert_new_chat',
        lambda user_id, form_data, db=None: ChatModel(
            id='chat-new',
            user_id=user_id,
            title=form_data.chat['title'],
            chat=form_data.chat,
            meta={},
            created_at=6000,
            updated_at=6005,
            archived=False,
            pinned=False,
            folder_id=None,
        ),
    )

    response = asyncio.run(
        chats_router.create_new_chat(
            chats_router.ChatForm(
                chat={
                    'title': 'Fresh Hermes chat',
                    'hermesSession': {
                        'profile': 'work',
                        'active_home': '/Users/martin/.hermes/profiles/work',
                    },
                    'history': {'messages': {}, 'currentId': None},
                }
            ),
            user=SimpleNamespace(id='user-1'),
            db=object(),
        )
    )

    assert response.meta == {
        'hermes': {
            'profile': 'work',
            'active_home': '/Users/martin/.hermes/profiles/work',
        }
    }
