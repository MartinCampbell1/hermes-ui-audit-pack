import asyncio
import json
import logging
import mimetypes
import selectors
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.chats import ChatImportForm, ChatModel, ChatResponse, Chats
from open_webui.models.files import Files
from open_webui.storage.provider import Storage
from open_webui.utils.access_control.files import has_access_to_file
from open_webui.utils.auth import get_verified_user
from open_webui.utils.hermes import (
    normalize_hermes_target_id,
    browse_hermes_workspace,
    build_hermes_context_summary,
    build_chat_import_payload,
    get_hermes_workspace_file_path,
    get_hermes_profiles,
    get_hermes_runtime,
    get_hermes_sessions,
    get_hermes_workspaces,
    get_imported_hermes_chat_map,
    load_hermes_session,
    refresh_imported_hermes_chat,
    HERMES_SEND_TIMEOUT_SECONDS,
    _build_hermes_session_message_result,
    _parse_hermes_runner_event,
    _parse_hermes_runner_result,
    send_hermes_runner_control_message,
    send_hermes_session_message,
    start_hermes_session_message_process,
    switch_hermes_profile,
    switch_hermes_workspace,
)


log = logging.getLogger(__name__)

router = APIRouter()


def _refresh_existing_imported_chat(
    db: Session,
    chat_id: str,
    user_id: str,
    session_payload: dict[str, Any],
) -> ChatModel | None:
    return refresh_imported_hermes_chat(
        db,
        chat_id,
        user_id,
        session_payload,
        build_import_payload_fn=build_chat_import_payload,
    )


def _extract_hermes_file_id(file_item: dict[str, Any]) -> str | None:
    nested_file = file_item.get('file') if isinstance(file_item.get('file'), dict) else {}

    for value in (
        nested_file.get('id'),
        file_item.get('file_id'),
        file_item.get('id') if file_item.get('type') == 'file' else None,
    ):
        normalized = str(value or '').strip()
        if normalized:
            return normalized

    return None


def _resolve_storage_path(path: str | None) -> str | None:
    normalized_path = str(path or '').strip()
    if not normalized_path:
        return None

    try:
        storage_path = Path(Storage.get_file(normalized_path)).expanduser().resolve()
    except Exception:
        storage_path = None

    if storage_path and storage_path.exists():
        return str(storage_path)

    try:
        local_path = Path(normalized_path).expanduser().resolve()
    except Exception:
        return None

    return str(local_path) if local_path.exists() else None


def _normalize_hermes_message_files(
    files: list[dict[str, Any]] | None,
    *,
    user: Any,
    db: Session,
) -> list[dict[str, Any]]:
    normalized_files: list[dict[str, Any]] = []

    for file_item in files or []:
        if not isinstance(file_item, dict):
            continue

        file_id = _extract_hermes_file_id(file_item)
        if file_id:
            file = Files.get_file_by_id(file_id, db=db)
            has_file_access = bool(
                file
                and (
                    file.user_id == getattr(user, 'id', None)
                    or getattr(user, 'role', None) == 'admin'
                    or has_access_to_file(file_id, 'read', user, db=db)
                )
            )
            if not file or not has_file_access:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='Attached file is not available.',
                )

            meta = file.meta if isinstance(file.meta, dict) else {}
            data = file.data if isinstance(file.data, dict) else {}
            normalized_files.append(
                {
                    'id': file.id,
                    'name': meta.get('name') or file.filename or file_item.get('name') or file.id,
                    'content_type': meta.get('content_type') or file_item.get('content_type'),
                    'size': meta.get('size') or file_item.get('size'),
                    'storage_path': _resolve_storage_path(file.path),
                    'content': data.get('content') if isinstance(data.get('content'), str) else None,
                    'source': 'open_webui_file',
                }
            )
            continue

        inline_content = file_item.get('content')
        inline_url = file_item.get('url')
        if not inline_content and not inline_url:
            continue

        normalized_files.append(
            {
                'name': file_item.get('name') or file_item.get('filename') or 'inline attachment',
                'type': file_item.get('type') or 'file',
                'content_type': file_item.get('content_type'),
                'size': file_item.get('size'),
                'content': inline_content if isinstance(inline_content, str) else None,
                'url': inline_url if isinstance(inline_url, str) else None,
                'source': 'inline',
            }
        )

    return normalized_files


class HermesRuntimeResponse(BaseModel):
    target_id: str = 'local'
    active_home: str
    active_profile: str
    agent_dir: Optional[str] = None
    python_path: str
    state_db_path: str
    session_dir: str
    warnings: list[str] = []


class HermesSessionListItem(BaseModel):
    target_id: str = 'local'
    session_id: str
    title: str
    model: Optional[str] = None
    message_count: int = 0
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    profile: Optional[str] = None
    source_tag: Optional[str] = None
    last_user_content: Optional[str] = None
    available_sources: list[str] = []
    imported_chat_id: Optional[str] = None
    imported_chat_archived: bool = False
    is_auxiliary_cli_session: bool = False
    time_range: Optional[str] = None


class HermesSessionsResponse(BaseModel):
    target_id: str = 'local'
    active_home: str
    active_profile: str
    items: list[HermesSessionListItem]


class HermesWorkspaceItem(BaseModel):
    path: str
    name: str
    is_active: bool = False


class HermesWorkspacesResponse(BaseModel):
    target_id: str = 'local'
    active_home: str
    active_profile: str
    last_workspace: Optional[str] = None
    items: list[HermesWorkspaceItem]


class HermesWorkspaceSwitchRequest(BaseModel):
    path: str


class HermesWorkspaceBrowseEntry(BaseModel):
    name: str
    type: str
    size: Optional[int] = None
    modified: Optional[int] = None


class HermesWorkspaceBrowseResponse(BaseModel):
    target_id: str = 'local'
    active_home: str
    active_profile: str
    root_path: str
    current_path: str
    entries: list[HermesWorkspaceBrowseEntry]


class HermesProfileListItem(BaseModel):
    name: str
    path: str
    is_default: bool = False
    is_active: bool = False
    model: Optional[str] = None
    provider: Optional[str] = None
    has_env: bool = False
    has_soul: bool = False
    has_memory: bool = False
    has_user_profile: bool = False
    memory_enabled: bool = False
    user_profile_enabled: bool = False
    gateway_running: bool = False
    skill_count: int = 0


class HermesProfilesResponse(BaseModel):
    target_id: str = 'local'
    active_home: str
    active_profile: str
    items: list[HermesProfileListItem]


class HermesProfileSwitchRequest(BaseModel):
    name: str


class HermesProfileSwitchResponse(HermesProfilesResponse):
    default_model: Optional[str] = None
    default_workspace: Optional[str] = None


class HermesImportRequest(BaseModel):
    session_id: str
    target_id: Optional[str] = None


class HermesImportResponse(BaseModel):
    target_id: str = 'local'
    session_id: str
    chat: ChatResponse
    already_imported: bool = False


class HermesSessionMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    model: Optional[str] = None
    workspace: Optional[str] = None
    client_request_id: Optional[str] = None
    target_id: Optional[str] = None
    files: Optional[list[dict[str, Any]]] = None


class HermesSessionMessageResponse(BaseModel):
    target_id: str = 'local'
    session_id: str
    answer: str = ''
    chat: dict
    meta: dict = {}
    result: dict = {}
    context_summary: Optional[dict[str, Any]] = None


class HermesSessionStreamStartResponse(BaseModel):
    target_id: str = 'local'
    stream_id: str
    session_id: str
    status: str = 'running'


class HermesSessionStreamStatusResponse(BaseModel):
    target_id: str = 'local'
    stream_id: str
    session_id: str
    status: str
    done: bool = False
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    context_summary: Optional[dict[str, Any]] = None
    approval_pending: Optional[dict[str, Any]] = None
    started_at: int
    updated_at: int


class HermesSessionApprovalRequest(BaseModel):
    stream_id: str
    choice: str


class HermesSessionApprovalResponse(BaseModel):
    target_id: str = 'local'
    stream_id: str
    session_id: str
    status: str
    choice: str
    request_id: str


@dataclass
class HermesSessionStreamState:
    stream_id: str
    session_id: str
    target_id: str = 'local'
    client_request_id: Optional[str] = None
    queue: Queue = field(default_factory=Queue)
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = 'starting'
    done: bool = False
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    context_summary: Optional[dict[str, Any]] = None
    cancel_requested: bool = False
    process: Any = None
    worker: Optional[threading.Thread] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    approval_pending: Optional[dict[str, Any]] = None
    approval_updated_at: Optional[float] = None
    control_waiters: dict[str, Queue] = field(default_factory=dict)
    stdin_lock: threading.Lock = field(default_factory=threading.Lock)


HERMES_SESSION_STREAM_TTL_SECONDS = 600
HERMES_STREAM_CONTROL_ACK_TIMEOUT_SECONDS = 8.0
HERMES_SESSION_APPROVAL_CHOICES = {'once', 'session', 'always', 'deny'}
HERMES_SESSION_STREAMS: dict[str, HermesSessionStreamState] = {}
HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID: dict[str, str] = {}
HERMES_SESSION_STREAMS_LOCK = threading.Lock()


def _format_sse_event(event: str, data: dict[str, Any]) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


def _poll_stream_queue(state: HermesSessionStreamState, timeout_seconds: float = 1.0):
    try:
        return state.queue.get(timeout=timeout_seconds)
    except Empty:
        return None


def _serialize_stream_state(state: HermesSessionStreamState) -> HermesSessionStreamStatusResponse:
    return HermesSessionStreamStatusResponse(
        target_id=state.target_id,
        stream_id=state.stream_id,
        session_id=state.session_id,
        status=state.status,
        done=state.done,
        error=state.error,
        result=dict(state.result) if state.result else None,
        context_summary=dict(state.context_summary) if state.context_summary else None,
        approval_pending=dict(state.approval_pending) if state.approval_pending else None,
        started_at=int(state.started_at),
        updated_at=int(state.updated_at),
    )


def _build_stream_client_request_key(
    target_id: str | None,
    client_request_id: str | None,
) -> str | None:
    normalized_client_request_id = (client_request_id or '').strip()
    if not normalized_client_request_id:
        return None

    return f'{normalize_hermes_target_id(target_id)}:{normalized_client_request_id}'


def _emit_stream_event(state: HermesSessionStreamState, event: str, data: dict[str, Any]):
    with state.lock:
        state.updated_at = time.time()
    state.queue.put({'event': event, 'data': data})


def _register_stream_control_waiter(state: HermesSessionStreamState, request_id: str) -> Queue:
    waiter: Queue = Queue(maxsize=1)
    with state.lock:
        state.control_waiters[request_id] = waiter
        state.updated_at = time.time()
    return waiter


def _pop_stream_control_waiter(state: HermesSessionStreamState, request_id: str) -> Optional[Queue]:
    with state.lock:
        waiter = state.control_waiters.pop(request_id, None)
        state.updated_at = time.time()
    return waiter


def _resolve_stream_control_waiter(
    state: HermesSessionStreamState,
    request_id: str,
    payload: dict[str, Any],
) -> bool:
    waiter = _pop_stream_control_waiter(state, request_id)
    if waiter is None:
        return False

    waiter.put(payload)
    return True


def _fail_stream_control_waiters(state: HermesSessionStreamState, payload: dict[str, Any]):
    with state.lock:
        waiters = list(state.control_waiters.values())
        state.control_waiters.clear()
        state.updated_at = time.time()

    for waiter in waiters:
        waiter.put(payload)


def _wait_for_stream_control_response(waiter: Queue, timeout_seconds: float) -> dict[str, Any]:
    try:
        return waiter.get(timeout=timeout_seconds)
    except Empty as exc:
        raise TimeoutError('Timed out waiting for Hermes approval acknowledgement.') from exc


def _apply_stream_runtime_event(
    state: HermesSessionStreamState,
    event_name: str,
    data: dict[str, Any],
):
    request_id = str(data.get('request_id') or '').strip()

    with state.lock:
        state.updated_at = time.time()

        if event_name == 'approval.pending':
            state.approval_pending = dict(data)
            state.approval_updated_at = state.updated_at
            if not state.done and not state.cancel_requested:
                state.status = 'waiting_approval'
        elif event_name == 'approval.resolved':
            state.approval_pending = None
            state.approval_updated_at = state.updated_at
            if not state.done and not state.cancel_requested:
                state.status = 'running'
        elif event_name == 'approval.error':
            state.approval_updated_at = state.updated_at
            if not state.done and state.approval_pending:
                state.status = 'waiting_approval'

    if request_id and event_name in {'approval.resolved', 'approval.error'}:
        _resolve_stream_control_waiter(
            state,
            request_id,
            {
                'event': event_name,
                'data': data,
            },
        )


def _prune_stream_registry():
    cutoff = time.time() - HERMES_SESSION_STREAM_TTL_SECONDS
    with HERMES_SESSION_STREAMS_LOCK:
        stale_stream_ids = [
            stream_id
            for stream_id, state in HERMES_SESSION_STREAMS.items()
            if state.done and state.updated_at < cutoff
        ]
        for stream_id in stale_stream_ids:
            state = HERMES_SESSION_STREAMS.pop(stream_id, None)
            if state and state.client_request_id:
                HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop(
                    _build_stream_client_request_key(state.target_id, state.client_request_id),
                    None,
                )
                HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop(state.client_request_id, None)


def _get_existing_stream_by_client_request_id(
    client_request_id: str | None,
    *,
    target_id: str | None = None,
) -> Optional[HermesSessionStreamState]:
    normalized_client_request_id = (client_request_id or '').strip()
    if not normalized_client_request_id:
        return None

    client_request_key = _build_stream_client_request_key(target_id, normalized_client_request_id)

    with HERMES_SESSION_STREAMS_LOCK:
        stream_id = (
            HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.get(client_request_key)
            if client_request_key
            else None
        )
        if stream_id is None:
            stream_id = HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.get(normalized_client_request_id)
        state = HERMES_SESSION_STREAMS.get(stream_id) if stream_id else None

        if state is None and stream_id:
            if client_request_key:
                HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop(client_request_key, None)
            HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID.pop(normalized_client_request_id, None)

    return state


def _get_stream_state(stream_id: str) -> HermesSessionStreamState:
    with HERMES_SESSION_STREAMS_LOCK:
        state = HERMES_SESSION_STREAMS.get(stream_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Hermes stream not found.',
        )
    return state


def _run_stream_worker(state: HermesSessionStreamState, context: dict[str, Any], process):
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    selector = selectors.DefaultSelector()
    final_event = 'cancel'
    final_payload: dict[str, Any] = {'message': 'Hermes response cancelled.'}
    final_status = 'cancelled'
    final_error: Optional[str] = None
    final_result: Optional[dict[str, Any]] = None

    try:
        with state.lock:
            state.status = 'running'
            state.process = process
            state.updated_at = time.time()

        if process.stdout is not None:
            selector.register(process.stdout, selectors.EVENT_READ, data='stdout')
        if process.stderr is not None:
            selector.register(process.stderr, selectors.EVENT_READ, data='stderr')

        deadline = time.monotonic() + HERMES_SEND_TIMEOUT_SECONDS

        while selector.get_map():
            if state.cancel_requested and process.poll() is None:
                process.terminate()

            if time.monotonic() > deadline and process.poll() is None:
                process.kill()
                raise TimeoutError('Hermes session stream timed out.')

            ready = selector.select(timeout=0.25)
            if not ready:
                continue

            for key, _ in ready:
                line = key.fileobj.readline()
                if line == '':
                    try:
                        selector.unregister(key.fileobj)
                    except Exception:
                        pass
                    continue

                line = line.rstrip('\n')
                if key.data == 'stdout':
                    stdout_lines.append(line)
                    event = _parse_hermes_runner_event(line)
                    if event:
                        event_name = str(event.get('event') or 'message')
                        event_data = event.get('data') or {}
                        _apply_stream_runtime_event(state, event_name, event_data)
                        _emit_stream_event(
                            state,
                            event_name,
                            event_data,
                        )
                else:
                    stderr_lines.append(line)

        return_code = process.wait(timeout=1)
        stdout_text = '\n'.join(stdout_lines)
        runner_result = None

        try:
            runner_result = _parse_hermes_runner_result(stdout_text)
        except Exception:
            runner_result = None

        if runner_result and not runner_result.get('error') and return_code == 0:
            result = _build_hermes_session_message_result(context, runner_result)
            final_event = 'done'
            final_payload = {
                'target_id': result.get('target_id') or state.target_id,
                'session_id': result['session_id'],
                'answer': result.get('answer') or '',
                'chat': result['chat_payload'].get('chat') or {},
                'meta': result['chat_payload'].get('meta') or {},
                'result': result.get('result') or {},
                'context_summary': result.get('context_summary'),
            }
            final_status = 'completed'
            final_result = final_payload
        elif state.cancel_requested:
            final_status = 'cancelled'
        else:
            error_message = None
            if runner_result and runner_result.get('error'):
                error_message = str(runner_result['error'])
            if not error_message:
                error_message = '\n'.join(stderr_lines).strip() or 'Hermes runner failed.'
            final_event = 'apperror'
            final_payload = {
                'message': error_message,
                'type': runner_result.get('error_type') if runner_result else 'HermesRunnerError',
            }
            final_status = 'error'
            final_error = error_message
    except Exception as exc:
        log.exception(exc)
        final_event = 'apperror'
        final_payload = {
            'message': str(exc),
            'type': type(exc).__name__,
        }
        final_status = 'error'
        final_error = str(exc)
        try:
            if process.poll() is None:
                process.kill()
        except Exception:
            pass
    finally:
        try:
            selector.close()
        except Exception:
            pass

        stdin = getattr(process, 'stdin', None)
        if stdin is not None:
            try:
                stdin.close()
            except Exception:
                pass

        _fail_stream_control_waiters(
            state,
            {
                'event': 'approval.error',
                'data': {
                    'message': final_payload.get('message')
                    or final_error
                    or 'Hermes approval request ended before it could be resolved.',
                    'type': final_payload.get('type') if isinstance(final_payload, dict) else None,
                },
            },
        )

        _emit_stream_event(state, final_event, final_payload)
        with state.lock:
            state.process = None
            state.status = final_status
            state.done = True
            state.error = final_error
            state.result = final_result
            state.context_summary = (
                dict(final_payload.get('context_summary'))
                if isinstance(final_payload, dict) and final_payload.get('context_summary')
                else state.context_summary
            )
            state.approval_pending = None
            state.approval_updated_at = time.time()
            state.updated_at = time.time()


@router.get('/runtime', response_model=HermesRuntimeResponse)
async def get_runtime_status(target_id: Optional[str] = None, user=Depends(get_verified_user)):
    try:
        return HermesRuntimeResponse(**get_hermes_runtime(target_id=target_id))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to load Hermes runtime status.',
        )


@router.get('/sessions', response_model=HermesSessionsResponse)
async def list_sessions(
    target_id: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    try:
        payload = get_hermes_sessions(target_id=normalize_hermes_target_id(target_id))
        imported_chat_map = get_imported_hermes_chat_map(
            db,
            user.id,
            [item.get('session_id') for item in payload.get('items', [])],
        )

        for item in payload.get('items', []):
            imported_chat = imported_chat_map.get(item.get('session_id'))
            if imported_chat:
                item['imported_chat_id'] = imported_chat['id']
                item['imported_chat_archived'] = imported_chat['archived']

        return HermesSessionsResponse(**payload)
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to load Hermes sessions.',
        )


@router.get('/workspaces', response_model=HermesWorkspacesResponse)
async def list_workspaces(target_id: Optional[str] = None, user=Depends(get_verified_user)):
    try:
        return HermesWorkspacesResponse(
            target_id=normalize_hermes_target_id(target_id),
            **get_hermes_workspaces(),
        )
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to load Hermes workspaces.',
        )


@router.post('/workspaces/switch', response_model=HermesWorkspacesResponse)
async def switch_workspace(form_data: HermesWorkspaceSwitchRequest, user=Depends(get_verified_user)):
    try:
        return HermesWorkspacesResponse(
            target_id=normalize_hermes_target_id(),
            **switch_hermes_workspace(form_data.path),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to switch Hermes workspace.',
        )


@router.get('/workspaces/browse', response_model=HermesWorkspaceBrowseResponse)
async def browse_workspace(
    path: Optional[str] = None,
    target_id: Optional[str] = None,
    user=Depends(get_verified_user),
):
    try:
        return HermesWorkspaceBrowseResponse(
            target_id=normalize_hermes_target_id(target_id),
            **browse_hermes_workspace(path),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to browse Hermes workspace.',
        )


@router.get('/workspaces/file')
async def get_workspace_file(path: str, user=Depends(get_verified_user)):
    try:
        file_path = get_hermes_workspace_file_path(path)
        media_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
        return FileResponse(
            file_path,
            media_type=media_type,
            filename=file_path.name,
            content_disposition_type='inline',
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to load Hermes workspace file.',
        )


@router.get('/profiles', response_model=HermesProfilesResponse)
async def list_profiles(target_id: Optional[str] = None, user=Depends(get_verified_user)):
    try:
        return HermesProfilesResponse(
            target_id=normalize_hermes_target_id(target_id),
            **get_hermes_profiles(),
        )
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to load Hermes profiles.',
        )


@router.post('/profiles/switch', response_model=HermesProfileSwitchResponse)
async def switch_profile(form_data: HermesProfileSwitchRequest, user=Depends(get_verified_user)):
    try:
        return HermesProfileSwitchResponse(
            target_id=normalize_hermes_target_id(),
            **switch_hermes_profile(form_data.name),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to switch Hermes profile.',
        )


@router.post('/sessions/import', response_model=HermesImportResponse)
async def import_session(
    form_data: HermesImportRequest,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    normalized_target_id = normalize_hermes_target_id(form_data.target_id)
    existing_chat_ref = get_imported_hermes_chat_map(db, user.id, [form_data.session_id]).get(
        form_data.session_id
    )
    session_payload: dict[str, Any] | None = None

    if existing_chat_ref:
        session_payload = load_hermes_session(form_data.session_id, target_id=normalized_target_id)
        if session_payload:
            refreshed_chat = _refresh_existing_imported_chat(
                db,
                existing_chat_ref['id'],
                user.id,
                session_payload,
            )
            if refreshed_chat:
                return HermesImportResponse(
                    target_id=normalized_target_id,
                    session_id=form_data.session_id,
                    chat=ChatResponse(**refreshed_chat.model_dump()),
                    already_imported=True,
                )

        existing_chat = Chats.get_chat_by_id_and_user_id(existing_chat_ref['id'], user.id, db=db)
        if existing_chat:
            return HermesImportResponse(
                target_id=normalized_target_id,
                session_id=form_data.session_id,
                chat=ChatResponse(**existing_chat.model_dump()),
                already_imported=True,
            )

    if not session_payload:
        session_payload = load_hermes_session(form_data.session_id, target_id=normalized_target_id)

    if not session_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Hermes session not found.',
        )

    try:
        import_payload = build_chat_import_payload(session_payload)
        imported_chat = Chats.import_chats(
            user.id,
            [ChatImportForm(**import_payload)],
            db=db,
        )[0]
        return HermesImportResponse(
            target_id=normalized_target_id,
            session_id=form_data.session_id,
            chat=ChatResponse(**imported_chat.model_dump()),
            already_imported=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to import Hermes session.',
        )


@router.post('/sessions/start', response_model=HermesSessionStreamStartResponse)
async def start_session_stream(
    form_data: HermesSessionMessageRequest,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    _prune_stream_registry()
    normalized_target_id = normalize_hermes_target_id(form_data.target_id)
    client_request_id = (form_data.client_request_id or '').strip() or None

    existing_state = _get_existing_stream_by_client_request_id(
        client_request_id,
        target_id=normalized_target_id,
    )
    if existing_state is not None:
        return HermesSessionStreamStartResponse(
            target_id=existing_state.target_id,
            stream_id=existing_state.stream_id,
            session_id=existing_state.session_id,
            status=existing_state.status,
        )

    try:
        normalized_files = _normalize_hermes_message_files(form_data.files, user=user, db=db)
        runner = start_hermes_session_message_process(
            form_data.session_id,
            form_data.message,
            model=form_data.model,
            workspace=form_data.workspace,
            emit_events=True,
            target_id=normalized_target_id,
            files=normalized_files,
        )
        context = runner['context']
        process = runner['process']

        stream_id = uuid.uuid4().hex
        state = HermesSessionStreamState(
            stream_id=stream_id,
            session_id=context['normalized_session_id'],
            target_id=context.get('target_id') or normalized_target_id,
            client_request_id=client_request_id,
            status='starting',
            context_summary=build_hermes_context_summary(context),
            process=process,
        )
        worker = threading.Thread(
            target=_run_stream_worker,
            args=(state, context, process),
            daemon=True,
            name=f'hermes-stream-{stream_id[:8]}',
        )
        state.worker = worker

        with HERMES_SESSION_STREAMS_LOCK:
            HERMES_SESSION_STREAMS[stream_id] = state
            if client_request_id:
                HERMES_SESSION_STREAMS_BY_CLIENT_REQUEST_ID[
                    _build_stream_client_request_key(state.target_id, client_request_id)
                ] = stream_id

        worker.start()

        return HermesSessionStreamStartResponse(
            target_id=state.target_id,
            stream_id=stream_id,
            session_id=context['normalized_session_id'],
            status='running',
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to start Hermes session stream.',
        )


@router.get('/sessions/stream')
async def stream_session_events(stream_id: str, user=Depends(get_verified_user)):
    state = _get_stream_state(stream_id)

    async def event_generator():
        try:
            while True:
                item = await asyncio.to_thread(_poll_stream_queue, state, 1.0)
                if item is None:
                    if state.done:
                        break
                    yield ': keep-alive\n\n'
                    continue

                yield _format_sse_event(item['event'], item['data'])

                if item['event'] in {'done', 'apperror', 'cancel'} and state.done:
                    break
        finally:
            _prune_stream_registry()

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    )


@router.get('/sessions/stream/status', response_model=HermesSessionStreamStatusResponse)
async def get_session_stream_status(stream_id: str, user=Depends(get_verified_user)):
    _prune_stream_registry()
    state = _get_stream_state(stream_id)
    return _serialize_stream_state(state)


@router.post('/sessions/approval', response_model=HermesSessionApprovalResponse)
async def submit_session_approval(
    form_data: HermesSessionApprovalRequest,
    user=Depends(get_verified_user),
):
    _prune_stream_registry()

    choice = (form_data.choice or '').strip().lower()
    if choice not in HERMES_SESSION_APPROVAL_CHOICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Unsupported Hermes approval choice.',
        )

    state = _get_stream_state(form_data.stream_id)

    with state.lock:
        if state.done:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Hermes stream is already complete.',
            )

        if not state.approval_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='No pending Hermes approval found.',
            )

        process = state.process
        session_id = state.session_id

    if process is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Hermes stream is not available for approval updates.',
        )

    request_id = uuid.uuid4().hex
    waiter = _register_stream_control_waiter(state, request_id)

    try:
        with state.stdin_lock:
            with state.lock:
                if state.done or state.process is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail='Hermes stream is no longer running.',
                    )

            send_hermes_runner_control_message(
                process,
                {
                    'action': 'approval.resolve',
                    'request_id': request_id,
                    'choice': choice,
                    'resolve_all': False,
                },
            )
    except HTTPException:
        _pop_stream_control_waiter(state, request_id)
        raise
    except Exception as exc:
        _resolve_stream_control_waiter(
            state,
            request_id,
            {
                'event': 'approval.error',
                'data': {
                    'request_id': request_id,
                    'message': str(exc),
                },
            },
        )

    try:
        control_response = await asyncio.to_thread(
            _wait_for_stream_control_response,
            waiter,
            HERMES_STREAM_CONTROL_ACK_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        _pop_stream_control_waiter(state, request_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc

    if control_response.get('event') == 'approval.error':
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(control_response.get('data', {}).get('message') or 'Hermes approval failed.'),
        )

    return HermesSessionApprovalResponse(
        target_id=state.target_id,
        stream_id=state.stream_id,
        session_id=session_id,
        status=state.status,
        choice=choice,
        request_id=request_id,
    )


@router.get('/sessions/cancel', response_model=HermesSessionStreamStatusResponse)
async def cancel_session_stream(stream_id: str, user=Depends(get_verified_user)):
    state = _get_stream_state(stream_id)

    with state.lock:
        if not state.done:
            state.cancel_requested = True
            state.status = 'cancelling'
            state.updated_at = time.time()
        process = state.process

    try:
        if process is not None and process.poll() is None:
            process.terminate()
    except Exception:
        pass

    return _serialize_stream_state(state)


@router.post('/sessions/send', response_model=HermesSessionMessageResponse)
async def send_session_message(
    form_data: HermesSessionMessageRequest,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    try:
        normalized_target_id = normalize_hermes_target_id(form_data.target_id)
        normalized_files = _normalize_hermes_message_files(form_data.files, user=user, db=db)
        result = send_hermes_session_message(
            form_data.session_id,
            form_data.message,
            model=form_data.model,
            workspace=form_data.workspace,
            target_id=normalized_target_id,
            files=normalized_files,
        )
        chat_payload = result.get('chat_payload') or {}
        return HermesSessionMessageResponse(
            target_id=result.get('target_id') or normalized_target_id,
            session_id=result['session_id'],
            answer=result.get('answer') or '',
            chat=chat_payload.get('chat') or {},
            meta=chat_payload.get('meta') or {},
            result=result.get('result') or {},
            context_summary=result.get('context_summary'),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Failed to send Hermes session message.',
        )
