import json
import hashlib
import logging
import os
import re
import selectors
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from open_webui.models.chats import Chat, ChatModel

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_PYTHON_WARNING = 'Hermes runtime fell back to system Python; agent venv was not found.'
HERMES_PROFILE_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')

HERMES_GENERATED_PROMPT_PREFIXES = (
    'review the conversation above and consider saving or updating a skill',
    '[your active task list was preserved across context compression]',
    "you are hermes memory's structured wiki compiler.",
)

HERMES_AUXILIARY_TITLE_PREFIXES = (
    'inspect ',
    'review ',
    'implement ',
    'analyze ',
    'investigate ',
    'audit ',
    'summarize ',
    'prepare ',
    'compare ',
    'explore ',
    'extract ',
    'identify ',
    'find ',
    'fix ',
    'draft ',
    'search ',
    'assess ',
)

HERMES_SESSION_DISCOVERY_LIMIT = 500
HERMES_SEND_TIMEOUT_SECONDS = 600
HERMES_RUNNER_EVENT_SENTINEL = '__OPEN_WEBUI_HERMES_EVENT__'
HERMES_RUNNER_RESULT_SENTINEL = '__OPEN_WEBUI_HERMES_RESULT__'
HERMES_DEFAULT_TARGET_ID = 'local'
HERMES_ATTACHMENT_TEXT_LIMIT = 12_000
HERMES_ATTACHMENT_TOTAL_TEXT_LIMIT = 36_000
HERMES_ATTACHMENT_MAX_FILES = 12
HERMES_ATTACHMENT_METADATA_LIMIT = 512
HERMES_ATTACHMENT_REFERENCE_LIMIT = 2_048


def normalize_hermes_target_id(target_id: str | None = None) -> str:
    normalized_target_id = str(target_id or '').strip()
    return normalized_target_id or HERMES_DEFAULT_TARGET_ID


def resolve_base_hermes_home() -> Path:
    base_override = os.getenv('HERMES_BASE_HOME', '').strip()
    if base_override:
        return Path(base_override).expanduser()

    hermes_home = os.getenv('HERMES_HOME', '').strip()
    if hermes_home:
        path = Path(hermes_home).expanduser()
        if path.parent.name == 'profiles':
            return path.parent.parent
        return path

    return Path.home() / '.hermes'


def get_active_profile_name() -> str:
    active_profile_path = resolve_base_hermes_home() / 'active_profile'
    if active_profile_path.exists():
        try:
            active_profile = active_profile_path.read_text(encoding='utf-8').strip()
            if active_profile:
                return active_profile
        except Exception:
            pass

    if not os.getenv('HERMES_BASE_HOME', '').strip():
        hermes_home = os.getenv('HERMES_HOME', '').strip()
        if hermes_home:
            hermes_home_path = Path(hermes_home).expanduser()
            if hermes_home_path.parent.name == 'profiles' and HERMES_PROFILE_NAME_RE.match(
                hermes_home_path.name
            ):
                return hermes_home_path.name

    return 'default'


def get_active_hermes_home() -> Path:
    base_home = resolve_base_hermes_home()
    active_profile = get_active_profile_name()

    if active_profile == 'default':
        return base_home

    profile_home = base_home / 'profiles' / active_profile
    if profile_home.is_dir():
        return profile_home

    return base_home


def _read_hermes_config(profile_home: Path) -> dict[str, Any]:
    config_path = profile_home / 'config.yaml'
    if not config_path.exists():
        return {}

    try:
        config = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}

    return config if isinstance(config, dict) else {}


def _read_profile_model_provider(profile_home: Path) -> tuple[str | None, str | None]:
    config = _read_hermes_config(profile_home)
    model_config = config.get('model')

    if isinstance(model_config, str):
        model = model_config.strip()
        return (model or None), None

    if isinstance(model_config, dict):
        model = str(model_config.get('default') or model_config.get('model') or '').strip()
        provider = str(model_config.get('provider') or '').strip()
        return (model or None), (provider or None)

    return None, None


def _is_gateway_running(profile_home: Path) -> bool:
    pid_file = profile_home / 'gateway.pid'
    if not pid_file.exists():
        return False

    try:
        raw = pid_file.read_text(encoding='utf-8').strip()
        if not raw:
            return False

        payload = json.loads(raw) if raw.startswith('{') else {'pid': int(raw)}
        pid = int(payload['pid'])
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _count_profile_skills(profile_home: Path) -> int:
    skills_dir = profile_home / 'skills'
    if not skills_dir.is_dir():
        return 0

    count = 0
    for skill_path in skills_dir.rglob('SKILL.md'):
        skill_path_text = str(skill_path)
        if '/.hub/' in skill_path_text or '/.git/' in skill_path_text:
            continue
        count += 1

    return count


def _build_profile_item(name: str, profile_home: Path, active_profile: str) -> dict[str, Any]:
    config = _read_hermes_config(profile_home)
    memory_config = config.get('memory') if isinstance(config.get('memory'), dict) else {}
    model, provider = _read_profile_model_provider(profile_home)
    memories_dir = profile_home / 'memories'

    return {
        'name': name,
        'path': str(profile_home),
        'is_default': name == 'default',
        'is_active': name == active_profile,
        'model': model,
        'provider': provider,
        'has_env': (profile_home / '.env').exists(),
        'has_soul': (profile_home / 'SOUL.md').exists(),
        'has_memory': (memories_dir / 'MEMORY.md').exists(),
        'has_user_profile': (memories_dir / 'USER.md').exists(),
        'memory_enabled': bool(memory_config.get('memory_enabled', False)),
        'user_profile_enabled': bool(memory_config.get('user_profile_enabled', False)),
        'gateway_running': _is_gateway_running(profile_home),
        'skill_count': _count_profile_skills(profile_home),
    }


def get_hermes_profiles() -> dict[str, Any]:
    base_home = resolve_base_hermes_home()
    active_home = get_active_hermes_home()
    active_profile = get_active_profile_name()
    profiles: list[dict[str, Any]] = []

    if base_home.is_dir():
        profiles.append(_build_profile_item('default', base_home, active_profile))

    profiles_root = base_home / 'profiles'
    if profiles_root.is_dir():
        for profile_home in sorted(profiles_root.iterdir()):
            if not profile_home.is_dir() or not HERMES_PROFILE_NAME_RE.match(profile_home.name):
                continue

            profiles.append(_build_profile_item(profile_home.name, profile_home, active_profile))

    return {
        'active_home': str(active_home),
        'active_profile': active_profile,
        'items': profiles,
    }


def switch_hermes_profile(name: str) -> dict[str, Any]:
    profile_name = str(name or '').strip()

    if not profile_name:
        raise ValueError('Profile name is required.')

    if profile_name != 'default' and not HERMES_PROFILE_NAME_RE.match(profile_name):
        raise ValueError('Invalid Hermes profile name.')

    base_home = resolve_base_hermes_home()
    if profile_name == 'default':
        active_home = base_home
    else:
        active_home = base_home / 'profiles' / profile_name
        if not active_home.is_dir():
            raise FileNotFoundError(f"Hermes profile '{profile_name}' does not exist.")

    active_profile_file = base_home / 'active_profile'
    active_profile_file.parent.mkdir(parents=True, exist_ok=True)
    active_profile_file.write_text(
        '' if profile_name == 'default' else profile_name, encoding='utf-8'
    )

    os.environ['HERMES_HOME'] = str(active_home)

    profiles_payload = get_hermes_profiles()
    workspaces_payload = get_hermes_workspaces()
    default_model, _default_provider = _read_profile_model_provider(active_home)

    return {
        **profiles_payload,
        'default_model': default_model,
        'default_workspace': workspaces_payload.get('last_workspace'),
    }


def _get_hermes_webui_state_dir(
    active_home: Path | None = None, active_profile: str | None = None
) -> Path:
    active_home = active_home or get_active_hermes_home()
    active_profile = active_profile or get_active_profile_name()

    state_dir_override = os.getenv('HERMES_WEBUI_STATE_DIR', '').strip()
    if state_dir_override:
        return Path(state_dir_override).expanduser()

    if active_profile != 'default':
        return active_home / 'webui_state'

    return resolve_base_hermes_home() / 'webui'


def _discover_default_workspace(active_home: Path, active_profile: str) -> Path:
    workspace_override = os.getenv('HERMES_WEBUI_DEFAULT_WORKSPACE', '').strip()
    if workspace_override:
        return Path(workspace_override).expanduser().resolve()

    config_path = active_home / 'config.yaml'
    if config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
        except Exception:
            config = {}

        for key in ('workspace', 'default_workspace'):
            workspace = config.get(key)
            if workspace:
                workspace_path = Path(str(workspace)).expanduser().resolve()
                if workspace_path.is_dir():
                    return workspace_path

        terminal_config = config.get('terminal')
        if isinstance(terminal_config, dict):
            cwd = str(terminal_config.get('cwd') or '').strip()
            if cwd and cwd != '.':
                workspace_path = Path(cwd).expanduser().resolve()
                if workspace_path.is_dir():
                    return workspace_path

    common_workspace = Path.home() / 'workspace'
    if common_workspace.is_dir():
        return common_workspace.resolve()

    return (_get_hermes_webui_state_dir(active_home, active_profile) / 'workspace').resolve()


def _normalize_workspace_name(path: Path, raw_name: str | None) -> str:
    normalized_name = str(raw_name or '').strip()
    if normalized_name.lower() == 'default' or not normalized_name:
        return 'Home' if normalized_name.lower() == 'default' else (path.name or 'Workspace')
    return normalized_name


def _clean_workspace_items(workspaces: list[Any]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for workspace in workspaces:
        if not isinstance(workspace, dict):
            continue

        raw_path = workspace.get('path')
        normalized_path = _normalize_path(raw_path)
        if not normalized_path:
            continue

        try:
            resolved_path = normalized_path.resolve()
        except Exception:
            resolved_path = normalized_path

        if not resolved_path.is_dir():
            continue

        path_key = str(resolved_path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)

        cleaned.append(
            {
                'path': path_key,
                'name': _normalize_workspace_name(resolved_path, workspace.get('name')),
            }
        )

    return cleaned


def _load_saved_workspaces(active_home: Path, active_profile: str) -> tuple[list[dict[str, str]], str | None]:
    state_dir = _get_hermes_webui_state_dir(active_home, active_profile)
    workspaces_file = state_dir / 'workspaces.json'
    last_workspace_file = state_dir / 'last_workspace.txt'

    workspaces: list[dict[str, str]] = []
    if workspaces_file.exists():
        try:
            loaded_workspaces = json.loads(workspaces_file.read_text(encoding='utf-8'))
        except Exception:
            loaded_workspaces = []

        if isinstance(loaded_workspaces, list):
            workspaces = _clean_workspace_items(loaded_workspaces)

    last_workspace: str | None = None
    if last_workspace_file.exists():
        try:
            raw_last_workspace = last_workspace_file.read_text(encoding='utf-8').strip()
        except Exception:
            raw_last_workspace = ''

        if raw_last_workspace:
            last_workspace_path = Path(raw_last_workspace).expanduser().resolve()
            if last_workspace_path.is_dir():
                last_workspace = str(last_workspace_path)

    return workspaces, last_workspace


def _write_last_workspace(active_home: Path, active_profile: str, workspace_path: Path) -> str:
    state_dir = _get_hermes_webui_state_dir(active_home, active_profile)
    state_dir.mkdir(parents=True, exist_ok=True)

    resolved_workspace = workspace_path.resolve()
    normalized_workspace = str(resolved_workspace)
    (state_dir / 'last_workspace.txt').write_text(normalized_workspace, encoding='utf-8')

    return normalized_workspace


def get_hermes_workspaces() -> dict[str, Any]:
    active_home = get_active_hermes_home()
    active_profile = get_active_profile_name()

    workspaces, last_workspace = _load_saved_workspaces(active_home, active_profile)
    default_workspace = _discover_default_workspace(active_home, active_profile)

    if not workspaces and default_workspace.is_dir():
        workspaces = [{'path': str(default_workspace), 'name': 'Home'}]

    effective_last_workspace = last_workspace
    if not effective_last_workspace and default_workspace.is_dir():
        effective_last_workspace = str(default_workspace)

    workspace_items = list(workspaces)
    workspace_paths = {item['path'] for item in workspace_items}

    if default_workspace.is_dir():
        default_workspace_path = str(default_workspace)
        if default_workspace_path not in workspace_paths:
            workspace_items.insert(
                0,
                {
                    'path': default_workspace_path,
                    'name': 'Home',
                },
            )
            workspace_paths.add(default_workspace_path)

    if (
        effective_last_workspace
        and Path(effective_last_workspace).is_dir()
        and effective_last_workspace not in workspace_paths
    ):
        current_path = Path(effective_last_workspace)
        workspace_items.insert(
            0,
            {
                'path': str(current_path),
                'name': _normalize_workspace_name(current_path, None),
            },
        )

    for workspace in workspace_items:
        workspace['is_active'] = workspace['path'] == effective_last_workspace

    return {
        'active_home': str(active_home),
        'active_profile': active_profile,
        'last_workspace': effective_last_workspace,
        'items': workspace_items,
    }


def switch_hermes_workspace(path: str) -> dict[str, Any]:
    normalized_path = _normalize_path(path)
    if normalized_path is None:
        raise ValueError('Workspace path is required.')

    resolved_path = normalized_path.resolve()
    if not resolved_path.is_dir():
        raise FileNotFoundError('Hermes workspace does not exist.')

    workspaces_payload = get_hermes_workspaces()
    available_workspace_paths = {
        str(Path(item.get('path', '')).expanduser().resolve())
        for item in workspaces_payload.get('items', [])
        if item.get('path')
    }

    resolved_workspace = str(resolved_path)
    if resolved_workspace not in available_workspace_paths:
        raise ValueError('Workspace is not available in Hermes context.')

    _write_last_workspace(get_active_hermes_home(), get_active_profile_name(), resolved_path)
    return get_hermes_workspaces()


def _get_active_hermes_workspace_root() -> Path:
    last_workspace = str(get_hermes_workspaces().get('last_workspace') or '').strip()
    if not last_workspace:
        raise FileNotFoundError('Hermes workspace is unavailable.')

    workspace_root = Path(last_workspace).expanduser().resolve()
    if not workspace_root.is_dir():
        raise FileNotFoundError('Hermes workspace does not exist.')

    return workspace_root


def _resolve_hermes_workspace_path(
    path: str | None = None, *, expect_directory: bool | None = None
) -> tuple[Path, Path]:
    workspace_root = _get_active_hermes_workspace_root()
    requested_path = _normalize_path(path) or workspace_root
    resolved_path = requested_path.resolve()

    try:
        resolved_path.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError('Path is outside the active Hermes workspace.') from exc

    if expect_directory is True and not resolved_path.is_dir():
        raise FileNotFoundError('Hermes workspace directory does not exist.')

    if expect_directory is False and not resolved_path.is_file():
        raise FileNotFoundError('Hermes workspace file does not exist.')

    return workspace_root, resolved_path


def browse_hermes_workspace(path: str | None = None) -> dict[str, Any]:
    active_home = get_active_hermes_home()
    active_profile = get_active_profile_name()
    workspace_root, current_path = _resolve_hermes_workspace_path(path, expect_directory=True)

    entries: list[dict[str, Any]] = []
    for child in sorted(current_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        try:
            stats = child.stat()
        except FileNotFoundError:
            continue

        entries.append(
            {
                'name': child.name,
                'type': 'directory' if child.is_dir() else 'file',
                'size': None if child.is_dir() else stats.st_size,
                'modified': int(stats.st_mtime),
            }
        )

    return {
        'active_home': str(active_home),
        'active_profile': active_profile,
        'root_path': str(workspace_root),
        'current_path': str(current_path),
        'entries': entries,
    }


def get_hermes_workspace_file_path(path: str) -> Path:
    _workspace_root, resolved_path = _resolve_hermes_workspace_path(path, expect_directory=False)
    return resolved_path


def _normalize_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None

    if isinstance(value, Path):
        return value.expanduser()

    value = value.strip()
    if not value:
        return None

    return Path(value).expanduser()


def _is_agent_checkout(path: Path | None) -> bool:
    return bool(path and path.is_dir() and (path / 'run_agent.py').exists())


def discover_hermes_agent_dir(repo_root: Path | None = None) -> Path | None:
    repo_root = repo_root or REPO_ROOT
    base_home = resolve_base_hermes_home()
    repo_parent = repo_root.parent

    candidates = [
        _normalize_path(os.getenv('HERMES_WEBUI_AGENT_DIR')),
        base_home / 'hermes-agent',
        repo_parent / 'hermes-agent',
        repo_parent if _is_agent_checkout(repo_parent) else None,
        Path.home() / '.hermes' / 'hermes-agent',
        Path.home() / 'hermes-agent',
    ]

    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue

        resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)

        if _is_agent_checkout(candidate):
            return candidate.resolve()

    return None


def discover_hermes_python(
    agent_dir: Path | None = None, repo_root: Path | None = None
) -> tuple[str, list[str]]:
    repo_root = repo_root or REPO_ROOT
    warnings: list[str] = []

    python_override = os.getenv('HERMES_WEBUI_PYTHON', '').strip() or os.getenv(
        'HERMES_PYTHON', ''
    ).strip()
    if python_override:
        return str(Path(python_override).expanduser()), warnings

    if agent_dir:
        for env_dir in ('venv', '.venv'):
            for relative_path in ('bin/python', 'Scripts/python.exe'):
                candidate = agent_dir / env_dir / relative_path
                if candidate.exists():
                    return str(candidate), warnings

    for relative_path in ('bin/python', 'Scripts/python.exe'):
        candidate = repo_root / '.venv' / relative_path
        if candidate.exists():
            return str(candidate), warnings

    system_python = shutil.which('python3') or shutil.which('python')
    if system_python:
        warnings.append(SYSTEM_PYTHON_WARNING)
        log.warning(SYSTEM_PYTHON_WARNING)
        return system_python, warnings

    warnings.append(SYSTEM_PYTHON_WARNING)
    log.warning(SYSTEM_PYTHON_WARNING)
    return 'python3', warnings


def _parse_timestamp(value: Any, default: int | None = None) -> int | None:
    if value is None or value == '':
        return default

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default

        try:
            return int(float(stripped))
        except ValueError:
            try:
                return int(
                    datetime.fromisoformat(stripped.replace('Z', '+00:00')).timestamp()
                )
            except ValueError:
                return default

    return default


def _normalize_message_content(content: Any) -> str:
    if content is None:
        return ''

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                text_parts.append(str(part.get('text') or ''))
            else:
                text_parts.append(json.dumps(part, ensure_ascii=False))
        return '\n'.join(part for part in text_parts if part)

    if isinstance(content, dict):
        if content.get('type') == 'text':
            return str(content.get('text') or '')
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def _normalize_session_text(content: Any) -> str:
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                text_parts.append(str(part.get('text') or ''))
        content = ' '.join(text_parts)
    elif isinstance(content, dict) and content.get('type') == 'text':
        content = str(content.get('text') or '')
    else:
        content = _normalize_message_content(content)

    return ' '.join(str(content or '').split()).strip()


def _is_generated_prompt(content: Any) -> bool:
    normalized = _normalize_session_text(content).lower()
    return any(normalized.startswith(prefix) for prefix in HERMES_GENERATED_PROMPT_PREFIXES)


def _extract_session_hygiene_metadata(messages: list[dict[str, Any]]) -> dict[str, Any]:
    user_messages: list[str] = []

    for message in messages or []:
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue

        normalized = _normalize_session_text(message.get('content'))
        if normalized:
            user_messages.append(normalized)

    if not user_messages:
        return {'is_auxiliary_cli_session': False}

    if all(_is_generated_prompt(message) for message in user_messages):
        return {'is_auxiliary_cli_session': True}

    non_generated_users = [message for message in user_messages if not _is_generated_prompt(message)]
    canonical_users = non_generated_users or user_messages
    first_user = canonical_users[0]
    is_auxiliary = (
        len(non_generated_users) == 1
        and len(first_user) >= 24
        and first_user[:1].isascii()
        and first_user[:1].isalpha()
        and any(first_user.lower().startswith(prefix) for prefix in HERMES_AUXILIARY_TITLE_PREFIXES)
    )

    return {'is_auxiliary_cli_session': is_auxiliary}


def _derive_title_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if not isinstance(message, dict):
            continue

        if message.get('role') != 'user':
            continue

        content = _normalize_message_content(message.get('content')).strip()
        if content:
            return content[:80]

    return 'Hermes Session'


def _get_session_json_path(hermes_home: Path, session_id: str) -> Path:
    return hermes_home / 'sessions' / f'session_{session_id}.json'


def _read_json_session(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _get_last_user_content(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue

        if message.get('role') != 'user':
            continue

        content = _normalize_message_content(message.get('content')).strip()
        if content:
            return content
    return None


def _get_latest_message_timestamp(messages: list[dict[str, Any]]) -> int | None:
    timestamps = [
        _parse_timestamp(message.get('timestamp'))
        for message in messages or []
        if isinstance(message, dict)
    ]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(timestamps) if timestamps else None


def _get_json_session_updated_at(
    data: dict[str, Any],
    messages: list[dict[str, Any]],
    fallback_timestamp: int,
) -> int | None:
    candidates = [
        _parse_timestamp(data.get('last_updated')),
        _get_latest_message_timestamp(messages),
        fallback_timestamp,
        _parse_timestamp(data.get('session_start')),
    ]
    candidates = [timestamp for timestamp in candidates if timestamp is not None]
    return max(candidates) if candidates else None


def _is_canonical_session_source(session: dict[str, Any]) -> bool:
    sources = set(session.get('available_sources') or [])
    return 'json' in sources or 'webui' in sources


def _get_state_db_session_metadata(
    hermes_home: Path,
    profile: str | None,
    session_id: str,
) -> dict[str, Any] | None:
    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return None

    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.model,
                    s.message_count,
                    s.source,
                    s.started_at,
                    COALESCE(MAX(m.timestamp), s.started_at) AS last_activity,
                    (
                        SELECT m2.content
                        FROM messages m2
                        WHERE m2.session_id = s.id AND m2.role = 'user'
                        ORDER BY m2.timestamp DESC
                        LIMIT 1
                    ) AS last_user_content
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                LIMIT 1
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return {
                'session_id': row['id'],
                'title': (row['title'] or '').strip() or 'Hermes Session',
                'model': row['model'] or None,
                'message_count': int(row['message_count'] or 0),
                'created_at': _parse_timestamp(row['started_at'], int(time.time())),
                'updated_at': _parse_timestamp(
                    row['last_activity'], _parse_timestamp(row['started_at'], int(time.time()))
                ),
                'profile': profile,
                'source_tag': row['source'] or 'cli',
                'available_sources': ['state_db'],
                'last_user_content': _normalize_message_content(row['last_user_content']).strip()
                or None,
                'is_auxiliary_cli_session': False,
            }
    except Exception as exc:
        log.warning('Failed to read Hermes state.db session metadata: %s', exc)
        return None


def _list_state_db_sessions(
    hermes_home: Path,
    profile: str | None,
    limit: int = HERMES_SESSION_DISCOVERY_LIMIT,
) -> list[dict[str, Any]]:
    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return []

    sessions: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.model,
                    s.message_count,
                    s.source,
                    s.started_at,
                    MAX(m.timestamp) AS last_activity,
                    (
                        SELECT m2.content
                        FROM messages m2
                        WHERE m2.session_id = s.id AND m2.role = 'user'
                        ORDER BY m2.timestamp DESC
                        LIMIT 1
                    ) AS last_user_content
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY COALESCE(MAX(m.timestamp), s.started_at) DESC
                LIMIT ?
                """,
                (max(0, limit),),
            )
            for row in cursor.fetchall():
                session_id = row['id']
                sessions.append(
                    {
                        'session_id': session_id,
                        'title': (row['title'] or '').strip() or 'Hermes Session',
                        'model': row['model'] or None,
                        'message_count': int(row['message_count'] or 0),
                        'created_at': _parse_timestamp(row['started_at'], int(time.time())),
                        'updated_at': _parse_timestamp(
                            row['last_activity'], _parse_timestamp(row['started_at'], int(time.time()))
                        ),
                        'profile': profile,
                        'source_tag': row['source'] or 'cli',
                        'available_sources': ['state_db'],
                        'last_user_content': _normalize_message_content(row['last_user_content']).strip()
                        or None,
                        'is_auxiliary_cli_session': False,
                    }
                )
    except Exception as exc:
        log.warning('Failed to read Hermes state.db sessions: %s', exc)
        return []

    return sessions


def _list_json_sessions(hermes_home: Path, profile: str | None) -> list[dict[str, Any]]:
    sessions_dir = hermes_home / 'sessions'
    if not sessions_dir.exists():
        return []

    sessions: list[dict[str, Any]] = []
    for path in sessions_dir.glob('session_*.json'):
        data = _read_json_session(path)
        if not data:
            continue

        messages = data.get('messages') if isinstance(data.get('messages'), list) else []
        session_id = str(data.get('session_id') or path.stem.removeprefix('session_'))
        fallback_timestamp = int(path.stat().st_mtime)
        updated_at = _get_json_session_updated_at(data, messages, fallback_timestamp)
        sessions.append(
            {
                'session_id': session_id,
                'title': str(data.get('title') or '').strip() or _derive_title_from_messages(messages),
                'model': data.get('model') or None,
                'message_count': int(data.get('message_count') or len(messages)),
                'created_at': _parse_timestamp(data.get('session_start'), fallback_timestamp),
                'updated_at': updated_at,
                'profile': profile,
                'source_tag': data.get('platform') or data.get('source') or 'cli',
                'available_sources': ['json'],
                'last_user_content': _get_last_user_content(messages),
            }
            | _extract_session_hygiene_metadata(messages)
        )

    sessions.sort(key=lambda item: item.get('updated_at') or 0, reverse=True)
    return sessions


def _list_webui_sessions(active_home: Path, profile: str | None) -> list[dict[str, Any]]:
    state_dir = _get_hermes_webui_state_dir(active_home, profile)
    sessions_dir = state_dir / 'sessions'
    index_path = sessions_dir / '_index.json'
    if not sessions_dir.exists():
        return []

    index_payload = []
    if index_path.exists():
        try:
            loaded_index = json.loads(index_path.read_text(encoding='utf-8'))
            if isinstance(loaded_index, list):
                index_payload = loaded_index
        except Exception as exc:
            log.warning('Failed to read Hermes WebUI session index: %s', exc)

    sessions: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()
    for item in index_payload:
        if not isinstance(item, dict):
            continue

        session_id = str(item.get('session_id') or '').strip()
        if not session_id:
            continue

        session_data = _read_json_session(sessions_dir / f'{session_id}.json') or {}
        messages = session_data.get('messages') if isinstance(session_data, dict) else []
        if not isinstance(messages, list):
            messages = []
        session_path = sessions_dir / f'{session_id}.json'
        fallback_timestamp = int(session_path.stat().st_mtime) if session_path.exists() else int(time.time())
        session_updated_at = max(
            _parse_timestamp(item.get('updated_at'), 0) or 0,
            _get_json_session_updated_at(session_data, messages, fallback_timestamp) or 0,
        )

        sessions.append(
            {
                'session_id': session_id,
                'title': str(item.get('title') or '').strip()
                or _derive_title_from_messages(messages)
                or 'Hermes Session',
                'model': item.get('model') or None,
                'message_count': int(item.get('message_count') or len(messages or [])),
                'created_at': _parse_timestamp(item.get('created_at'), int(time.time())),
                'updated_at': session_updated_at,
                'profile': item.get('profile') or profile,
                'source_tag': 'webui',
                'available_sources': ['webui'],
                'last_user_content': _get_last_user_content(messages or []),
                'is_auxiliary_cli_session': False,
            }
        )
        seen_session_ids.add(session_id)

    for path in sessions_dir.glob('*.json'):
        if path.name == '_index.json':
            continue

        session_id = path.stem
        if session_id in seen_session_ids:
            continue

        session_data = _read_json_session(path) or {}
        messages = session_data.get('messages') if isinstance(session_data, dict) else []
        if not isinstance(messages, list):
            messages = []

        fallback_timestamp = int(path.stat().st_mtime)
        sessions.append(
            {
                'session_id': str(session_data.get('session_id') or session_id),
                'title': str(session_data.get('title') or '').strip()
                or _derive_title_from_messages(messages)
                or 'Hermes Session',
                'model': session_data.get('model') or None,
                'message_count': int(session_data.get('message_count') or len(messages or [])),
                'created_at': _parse_timestamp(session_data.get('session_start'), fallback_timestamp),
                'updated_at': _get_json_session_updated_at(
                    session_data,
                    messages,
                    fallback_timestamp,
                ),
                'profile': session_data.get('profile') or profile,
                'source_tag': 'webui',
                'available_sources': ['webui'],
                'last_user_content': _get_last_user_content(messages or []),
                'is_auxiliary_cli_session': False,
            }
        )

    sessions.sort(key=lambda item: item.get('updated_at') or 0, reverse=True)
    return sessions


def get_hermes_sessions(
    limit: int = HERMES_SESSION_DISCOVERY_LIMIT,
    *,
    target_id: str | None = None,
) -> dict[str, Any]:
    hermes_home = get_active_hermes_home()
    active_profile = get_active_profile_name()
    normalized_target_id = normalize_hermes_target_id(target_id)
    combined_map: dict[str, dict[str, Any]] = {}

    for source_sessions in (
        _list_state_db_sessions(hermes_home, active_profile, limit=max(limit, HERMES_SESSION_DISCOVERY_LIMIT)),
        _list_json_sessions(hermes_home, active_profile),
        _list_webui_sessions(hermes_home, active_profile),
    ):
        for session in source_sessions:
            session_id = session.get('session_id')
            if not session_id:
                continue

            if session_id not in combined_map:
                combined_map[session_id] = dict(session)
                continue

            existing = combined_map[session_id]
            session_updated_at = session.get('updated_at') or 0
            existing_updated_at = existing.get('updated_at') or 0
            session_is_fresher = session_updated_at > existing_updated_at
            session_is_canonical = _is_canonical_session_source(session)
            existing_is_canonical = _is_canonical_session_source(existing)

            if (
                (existing.get('title') in ('', 'Hermes Session') and session.get('title'))
                or (session_is_canonical and not existing_is_canonical and session.get('title'))
            ):
                existing['title'] = session['title']

            if (not existing.get('model') or (session_is_canonical and not existing_is_canonical)) and session.get('model'):
                existing['model'] = session['model']

            if (session.get('message_count') or 0) > (existing.get('message_count') or 0):
                existing['message_count'] = session['message_count']

            if session_is_fresher:
                existing['updated_at'] = session['updated_at']

            if not existing.get('created_at') and session.get('created_at'):
                existing['created_at'] = session['created_at']

            if (
                (not existing.get('last_user_content') or (session_is_canonical and not existing_is_canonical))
                and session.get('last_user_content')
            ):
                existing['last_user_content'] = session['last_user_content']

            if (
                (not existing.get('profile') or (session_is_canonical and not existing_is_canonical))
                and session.get('profile')
            ):
                existing['profile'] = session['profile']

            if (
                (not existing.get('source_tag') or (session_is_canonical and not existing_is_canonical))
                and session.get('source_tag')
            ):
                existing['source_tag'] = session['source_tag']

            existing_sources = set(existing.get('available_sources') or [])
            existing_sources.update(session.get('available_sources') or [])
            existing['available_sources'] = sorted(existing_sources)

            if session.get('is_auxiliary_cli_session'):
                existing['is_auxiliary_cli_session'] = True

    items = sorted(
        combined_map.values(), key=lambda item: item.get('updated_at') or 0, reverse=True
    )[:limit]
    for item in items:
        item['target_id'] = normalize_hermes_target_id(item.get('target_id') or normalized_target_id)

    return {
        'target_id': normalized_target_id,
        'active_home': str(hermes_home),
        'active_profile': active_profile,
        'items': items,
    }


def _get_imported_hermes_session_id(chat_item: Any) -> str | None:
    meta = chat_item.meta if isinstance(chat_item.meta, dict) else {}
    chat = chat_item.chat if isinstance(chat_item.chat, dict) else {}

    meta_session_id = meta.get('hermes', {}).get('session_id')
    if isinstance(meta_session_id, str) and meta_session_id.strip():
        return meta_session_id.strip()

    chat_session_id = chat.get('hermesSession', {}).get('session_id')
    if isinstance(chat_session_id, str) and chat_session_id.strip():
        return chat_session_id.strip()

    return None


def get_imported_hermes_chat_map(
    db: Session, user_id: str, session_ids: list[str]
) -> dict[str, dict[str, Any]]:
    normalized_session_ids = sorted(
        {session_id.strip() for session_id in session_ids if isinstance(session_id, str) and session_id.strip()}
    )
    if not normalized_session_ids:
        return {}

    query = db.query(Chat).filter(Chat.user_id == user_id)
    dialect_name = db.bind.dialect.name if db.bind else ''

    if dialect_name == 'sqlite':
        meta_session_id = func.json_extract(Chat.meta, '$.hermes.session_id')
        chat_session_id = func.json_extract(Chat.chat, '$.hermesSession.session_id')
        query = query.filter(
            or_(
                meta_session_id.in_(normalized_session_ids),
                chat_session_id.in_(normalized_session_ids),
            )
        )
    elif dialect_name == 'postgresql':
        query = query.filter(
            or_(
                Chat.meta['hermes']['session_id'].astext.in_(normalized_session_ids),
                Chat.chat['hermesSession']['session_id'].astext.in_(normalized_session_ids),
            )
        )

    query = query.order_by(Chat.archived.asc(), Chat.updated_at.desc(), Chat.id)

    imported_chat_map: dict[str, dict[str, Any]] = {}
    for chat_item in query.all():
        session_id = _get_imported_hermes_session_id(chat_item)
        if not session_id or session_id not in normalized_session_ids or session_id in imported_chat_map:
            continue

        imported_chat_map[session_id] = {
            'id': chat_item.id,
            'title': chat_item.title or 'New Chat',
            'created_at': chat_item.created_at,
            'updated_at': chat_item.updated_at,
            'archived': bool(chat_item.archived),
        }

        if len(imported_chat_map) == len(normalized_session_ids):
            break

    return imported_chat_map


def refresh_imported_hermes_chat(
    db: Session,
    chat_id: str,
    user_id: str,
    session_payload: dict[str, Any],
    *,
    build_import_payload_fn=None,
) -> ChatModel | None:
    chat_item = db.query(Chat).filter_by(id=chat_id, user_id=user_id).first()
    if chat_item is None:
        return None

    build_import_payload_fn = build_import_payload_fn or build_chat_import_payload
    import_payload = build_import_payload_fn(session_payload)
    imported_chat_payload = (
        import_payload.get('chat') if isinstance(import_payload.get('chat'), dict) else {}
    )
    imported_meta_payload = (
        import_payload.get('meta') if isinstance(import_payload.get('meta'), dict) else {}
    )

    existing_chat_payload = chat_item.chat if isinstance(chat_item.chat, dict) else {}
    existing_meta_payload = chat_item.meta if isinstance(chat_item.meta, dict) else {}

    merged_chat_payload = {
        **existing_chat_payload,
        **{
            key: value
            for key, value in imported_chat_payload.items()
            if key not in {'files', 'params', 'tags'}
        },
    }
    merged_chat_payload['files'] = existing_chat_payload.get(
        'files', imported_chat_payload.get('files', [])
    )
    merged_chat_payload['params'] = existing_chat_payload.get(
        'params', imported_chat_payload.get('params', {})
    )
    merged_chat_payload['tags'] = existing_chat_payload.get(
        'tags', imported_chat_payload.get('tags', [])
    )

    merged_meta_payload = {**existing_meta_payload, **imported_meta_payload}
    existing_hermes_meta = (
        existing_meta_payload.get('hermes')
        if isinstance(existing_meta_payload.get('hermes'), dict)
        else {}
    )
    imported_hermes_meta = (
        imported_meta_payload.get('hermes')
        if isinstance(imported_meta_payload.get('hermes'), dict)
        else {}
    )
    if existing_hermes_meta or imported_hermes_meta:
        merged_meta_payload['hermes'] = {**existing_hermes_meta, **imported_hermes_meta}

    chat_item.chat = merged_chat_payload
    chat_item.title = imported_chat_payload.get('title') or chat_item.title or 'New Chat'
    chat_item.meta = merged_meta_payload
    chat_item.updated_at = int(session_payload.get('updated_at') or chat_item.updated_at or time.time())

    db.commit()
    db.refresh(chat_item)

    return ChatModel.model_validate(chat_item)


def _read_state_db_messages(db_path: Path, session_id: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT role, content, tool_call_id, tool_calls, tool_name, timestamp, reasoning, reasoning_details
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            )

            messages = []
            for row in cursor.fetchall():
                tool_calls = row['tool_calls']
                if tool_calls:
                    try:
                        tool_calls = json.loads(tool_calls)
                    except json.JSONDecodeError:
                        pass

                reasoning_details = row['reasoning_details']
                if reasoning_details:
                    try:
                        reasoning_details = json.loads(reasoning_details)
                    except json.JSONDecodeError:
                        pass

                messages.append(
                    {
                        'role': row['role'] or 'assistant',
                        'content': row['content'] or '',
                        'tool_call_id': row['tool_call_id'],
                        'tool_calls': tool_calls,
                        'tool_name': row['tool_name'],
                        'timestamp': row['timestamp'],
                        'reasoning': row['reasoning'],
                        'reasoning_details': reasoning_details,
                    }
                )

            return messages
    except Exception as exc:
        log.warning('Failed to read Hermes session messages from state.db: %s', exc)
        return []


def load_hermes_session(
    session_id: str,
    sessions_payload: dict[str, Any] | None = None,
    *,
    target_id: str | None = None,
) -> dict[str, Any] | None:
    sessions_payload = sessions_payload or get_hermes_sessions(
        limit=HERMES_SESSION_DISCOVERY_LIMIT,
        target_id=target_id,
    )
    hermes_home = Path(sessions_payload['active_home'])
    active_profile = sessions_payload.get('active_profile')
    normalized_target_id = normalize_hermes_target_id(
        target_id or sessions_payload.get('target_id')
    )
    session_map = {
        session['session_id']: session for session in sessions_payload['items'] if session.get('session_id')
    }

    json_path = _get_session_json_path(hermes_home, session_id)
    json_data = _read_json_session(json_path) if json_path.exists() else None
    json_messages = (
        json_data.get('messages')
        if json_data and isinstance(json_data.get('messages'), list)
        else []
    )
    json_fallback_timestamp = int(json_path.stat().st_mtime) if json_path.exists() else int(time.time())

    state_metadata = _get_state_db_session_metadata(hermes_home, active_profile, session_id)
    state_messages = _read_state_db_messages(hermes_home / 'state.db', session_id)

    # Hermes session_<id>.json is the canonical conversation artifact.
    # state.db is only a discovery/freshness index and a recovery fallback when
    # the canonical JSON transcript is unavailable or empty.
    use_state_messages = bool(state_messages) and not json_messages

    messages = state_messages if use_state_messages else json_messages
    messages = _enrich_tool_message_names(messages)

    if not messages:
        return None

    session_info = {
        **(state_metadata or {}),
        **session_map.get(session_id, {}),
    }
    title = (
        str(json_data.get('title') or '').strip()
        if json_data and not use_state_messages
        else str(session_info.get('title') or '').strip()
    ) or _derive_title_from_messages(messages)

    model = (
        (json_data.get('model') if json_data else None)
        or session_info.get('model')
        or 'unknown'
    )
    source_tag = (
        (None if use_state_messages else (json_data.get('platform') if json_data else None))
        or (None if use_state_messages else (json_data.get('source') if json_data else None))
        or session_info.get('source_tag')
        or 'cli'
    )
    available_sources = set(session_info.get('available_sources') or [])
    if json_data:
        available_sources.add('json')
    if state_metadata or state_messages:
        available_sources.add('state_db')

    return {
        'session_id': session_id,
        'target_id': normalized_target_id,
        'runtime_target_id': normalized_target_id,
        'title': title,
        'model': model,
        'messages': messages,
        'created_at': session_info.get('created_at')
        or _parse_timestamp(json_data.get('session_start') if json_data else None, json_fallback_timestamp),
        'updated_at': session_info.get('updated_at')
        or _parse_timestamp(json_data.get('last_updated') if json_data else None, json_fallback_timestamp),
        'profile': active_profile,
        'source_tag': source_tag,
        'active_home': str(hermes_home),
        'available_sources': sorted(available_sources),
    }


def _get_tool_call_name(tool_call: Any) -> str | None:
    if not isinstance(tool_call, dict):
        return None

    function_payload = tool_call.get('function')
    if isinstance(function_payload, dict):
        function_name = str(function_payload.get('name') or '').strip()
        if function_name:
            return function_name

    direct_name = str(tool_call.get('name') or '').strip()
    return direct_name or None


def _enrich_tool_message_names(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return messages

    tool_names_by_call_id: dict[str, str] = {}
    enriched_messages: list[dict[str, Any]] = []

    for source_message in messages:
        message = dict(source_message)

        tool_calls = message.get('tool_calls')
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue

                tool_call_id = str(tool_call.get('call_id') or tool_call.get('id') or '').strip()
                tool_name = _get_tool_call_name(tool_call)
                if tool_call_id and tool_name:
                    tool_names_by_call_id[tool_call_id] = tool_name

        if str(message.get('role') or '').strip() == 'tool' and not message.get('tool_name'):
            tool_call_id = str(message.get('tool_call_id') or '').strip()
            inferred_tool_name = tool_names_by_call_id.get(tool_call_id)
            if inferred_tool_name:
                message['tool_name'] = inferred_tool_name

        enriched_messages.append(message)

    return enriched_messages


def get_hermes_runtime(*, target_id: str | None = None) -> dict[str, Any]:
    active_home = get_active_hermes_home()
    agent_dir = discover_hermes_agent_dir()
    python_path, warnings = discover_hermes_python(agent_dir)
    normalized_target_id = normalize_hermes_target_id(target_id)

    return {
        'target_id': normalized_target_id,
        'active_home': str(active_home),
        'active_profile': get_active_profile_name(),
        'agent_dir': str(agent_dir) if agent_dir else None,
        'python_path': python_path,
        'state_db_path': str(active_home / 'state.db'),
        'session_dir': str(active_home / 'sessions'),
        'warnings': warnings,
    }


def _format_import_content(message: dict[str, Any]) -> str:
    role = str(message.get('role') or 'assistant')
    content = _normalize_message_content(message.get('content')).strip()

    if role == 'tool':
        tool_name = str(message.get('tool_name') or 'tool').strip()
        if content:
            return f'[Tool: {tool_name}]\n{content}'
        return f'[Tool: {tool_name}]'

    return content


def _build_stable_import_message_id(
    session_id: str | None,
    source_message: dict[str, Any],
    index: int,
) -> str:
    payload = json.dumps(
        {
            'session_id': session_id,
            'index': index,
            'role': source_message.get('role'),
            'timestamp': source_message.get('timestamp'),
            'content': _normalize_message_content(source_message.get('content')),
            'tool_call_id': source_message.get('tool_call_id'),
            'tool_name': source_message.get('tool_name'),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode('utf-8')).hexdigest()
    return f"hermes-{digest[:24]}"


def build_chat_import_payload(session: dict[str, Any]) -> dict[str, Any]:
    history_messages: dict[str, dict[str, Any]] = {}
    ordered_messages: list[dict[str, Any]] = []
    previous_message_id: str | None = None
    current_message_id: str | None = None

    for index, source_message in enumerate(session.get('messages') or []):
        message_id = _build_stable_import_message_id(session.get('session_id'), source_message, index)
        role = str(source_message.get('role') or 'assistant')
        timestamp = _parse_timestamp(source_message.get('timestamp'), int(time.time())) or int(
            time.time()
        )

        chat_message: dict[str, Any] = {
            'id': message_id,
            'parentId': previous_message_id,
            'childrenIds': [],
            'role': role,
            'content': _format_import_content(source_message),
            'timestamp': timestamp,
            'sourceRole': role,
        }

        if previous_message_id:
            history_messages[previous_message_id]['childrenIds'] = [message_id]

        if role != 'user':
            chat_message['done'] = True
            if session.get('model'):
                chat_message['model'] = session['model']
                chat_message['modelName'] = 'Hermes'
                chat_message['modelIdx'] = 0

        if source_message.get('tool_name'):
            chat_message['toolName'] = source_message['tool_name']
        if source_message.get('tool_call_id'):
            chat_message['toolCallId'] = source_message['tool_call_id']
        if source_message.get('tool_calls') is not None:
            chat_message['toolCalls'] = source_message['tool_calls']
        if source_message.get('reasoning'):
            chat_message['reasoning'] = source_message['reasoning']
        if source_message.get('reasoning_details') is not None:
            chat_message['reasoningDetails'] = source_message['reasoning_details']

        history_messages[message_id] = chat_message
        ordered_messages.append(chat_message)
        previous_message_id = message_id
        current_message_id = message_id

    if current_message_id is None:
        raise ValueError('Hermes session contains no importable messages.')

    model = session.get('model')
    title = str(session.get('title') or '').strip() or _derive_title_from_messages(
        session.get('messages') or []
    )
    runtime_target_id = normalize_hermes_target_id(
        session.get('runtime_target_id') or session.get('target_id')
    )

    return {
        'chat': {
            'title': title,
            'models': [model] if model and model != 'unknown' else [],
            'history': {
                'messages': history_messages,
                'currentId': current_message_id,
            },
            'messages': ordered_messages,
            'params': {},
            'files': [],
            'tags': [],
            'timestamp': (session.get('updated_at') or int(time.time())) * 1000,
	            'hermesSession': {
	                'session_id': session.get('session_id'),
	                'target_id': runtime_target_id,
	                'runtime_target_id': runtime_target_id,
	                'model': model,
	                'source': 'hermes_cli',
	                'source_tag': session.get('source_tag'),
	                'active_home': session.get('active_home'),
	                'profile': session.get('profile'),
            },
        },
        'meta': {
	            'hermes': {
	                'session_id': session.get('session_id'),
	                'target_id': runtime_target_id,
	                'runtime_target_id': runtime_target_id,
	                'model': model,
	                'source': 'hermes_cli',
	                'source_tag': session.get('source_tag'),
	                'active_home': session.get('active_home'),
                'profile': session.get('profile'),
            }
        },
        'pinned': False,
        'created_at': int(session.get('created_at') or int(time.time())),
        'updated_at': int(session.get('updated_at') or int(time.time())),
    }


def _get_default_hermes_workspace_path() -> str:
    try:
        workspaces = get_hermes_workspaces()
        active_workspace = next(
            (item for item in workspaces.get('items', []) if item.get('is_active')), None
        )
        workspace = (
            active_workspace.get('path')
            if active_workspace
            else workspaces.get('last_workspace')
        )
        if workspace:
            return str(Path(workspace).expanduser().resolve())
    except Exception as exc:
        log.debug('Failed to resolve default Hermes workspace: %s', exc)

    return str(Path.home())


def _get_default_hermes_model() -> str | None:
    try:
        profiles = get_hermes_profiles()
        active_profile = next(
            (item for item in profiles.get('items', []) if item.get('is_active')), None
        )
        model = active_profile.get('model') if active_profile else None
        if isinstance(model, str) and model.strip():
            return model.strip()
    except Exception as exc:
        log.debug('Failed to resolve default Hermes model: %s', exc)

    return None


def _normalize_hermes_attachment_value(
    value: Any,
    *,
    limit: int = HERMES_ATTACHMENT_METADATA_LIMIT,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > limit:
        return normalized[:limit].rstrip() + '...'

    return normalized


def _truncate_hermes_attachment_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False

    return text[:limit].rstrip(), True


def _render_hermes_attachment_context(files: list[dict[str, Any]] | None = None) -> str:
    if not files:
        return ''

    rendered_files: list[str] = []
    remaining_text_budget = HERMES_ATTACHMENT_TOTAL_TEXT_LIMIT

    renderable_files = [file_item for file_item in files if isinstance(file_item, dict)][
        :HERMES_ATTACHMENT_MAX_FILES
    ]

    for index, file_item in enumerate(renderable_files, start=1):
        if not isinstance(file_item, dict):
            continue

        name = _normalize_hermes_attachment_value(
            file_item.get('name') or file_item.get('filename') or file_item.get('id')
        )
        content_type = _normalize_hermes_attachment_value(
            file_item.get('content_type') or file_item.get('type')
        )
        storage_path = _normalize_hermes_attachment_value(
            file_item.get('storage_path') or file_item.get('path'),
            limit=HERMES_ATTACHMENT_REFERENCE_LIMIT,
        )
        source_url = _normalize_hermes_attachment_value(
            file_item.get('url'),
            limit=HERMES_ATTACHMENT_REFERENCE_LIMIT,
        )
        size = file_item.get('size')
        content = file_item.get('content')

        lines = [f'{index}. {name or "attached-file"}']
        if content_type:
            lines.append(f'- Type: {content_type}')
        if isinstance(size, int) and size >= 0:
            lines.append(f'- Size: {size} bytes')
        if storage_path:
            lines.append(f'- Accessible file path: {storage_path}')
        elif source_url and not source_url.startswith('data:'):
            lines.append(f'- Reference: {source_url}')

        if isinstance(content, str) and content.strip() and remaining_text_budget > 0:
            per_file_limit = min(HERMES_ATTACHMENT_TEXT_LIMIT, remaining_text_budget)
            snippet, truncated = _truncate_hermes_attachment_text(content.strip(), per_file_limit)
            remaining_text_budget -= len(snippet)
            lines.extend(
                [
                    '- Extracted content:',
                    '```text',
                    snippet,
                    '```',
                ]
            )
            if truncated:
                lines.append('- Extracted content was truncated for this turn.')
        elif content_type and content_type.startswith('image/') and storage_path:
            lines.append('- Image attachment. Inspect the accessible file path if visual details matter.')
        elif content_type and content_type.startswith('image/'):
            lines.append('- Image attachment metadata only; no accessible local path was provided.')
        elif storage_path:
            lines.append('- Binary or unprocessed attachment. Inspect the accessible file path if needed.')

        rendered_files.append('\n'.join(lines))

    if not rendered_files:
        return ''

    if len(files) > HERMES_ATTACHMENT_MAX_FILES:
        rendered_files.append(
            f'Only the first {HERMES_ATTACHMENT_MAX_FILES} attachments were included in this turn.'
        )

    return (
        '[Attached files]\n'
        + '\n\n'.join(rendered_files)
        + '\n[End attached files]'
    )


def _build_hermes_message_with_attachments(message: str, files: list[dict[str, Any]] | None = None) -> str:
    attachment_context = _render_hermes_attachment_context(files)
    normalized_message = str(message or '').strip()

    if not attachment_context:
        return normalized_message

    return f'{attachment_context}\n\nUser request:\n{normalized_message}'


def _resolve_hermes_send_context(
    session_id: str | None,
    message: str,
    *,
    model: str | None = None,
    workspace: str | None = None,
    target_id: str | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_session_id = str(session_id or '').strip()
    normalized_message = str(message or '').strip()
    normalized_files = files or []
    if not normalized_message and not normalized_files:
        raise ValueError('Hermes message is required.')
    if not normalized_message and normalized_files:
        normalized_message = 'Please review the attached file(s).'

    runtime = get_hermes_runtime(target_id=target_id)
    normalized_target_id = normalize_hermes_target_id(target_id or runtime.get('target_id'))
    if not normalized_session_id:
        normalized_session_id = uuid.uuid4().hex[:12]

    session_payload = load_hermes_session(normalized_session_id, target_id=normalized_target_id)
    if not session_payload and str(session_id or '').strip():
        raise FileNotFoundError('Hermes session not found.')
    if not session_payload:
        session_payload = {
            'session_id': normalized_session_id,
            'target_id': normalized_target_id,
            'runtime_target_id': normalized_target_id,
            'title': 'New Hermes session',
            'model': model or _get_default_hermes_model() or 'unknown',
            'messages': [],
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'profile': runtime.get('active_profile'),
            'source_tag': 'open_webui',
            'active_home': runtime.get('active_home'),
            'available_sources': ['state_db'],
        }
    else:
        session_payload = {
            **session_payload,
            'target_id': normalize_hermes_target_id(
                session_payload.get('target_id')
                or session_payload.get('runtime_target_id')
                or normalized_target_id
            ),
            'runtime_target_id': normalize_hermes_target_id(
                session_payload.get('runtime_target_id')
                or session_payload.get('target_id')
                or normalized_target_id
            ),
        }

    agent_dir = runtime.get('agent_dir')
    python_path = runtime.get('python_path')
    if not agent_dir or not python_path:
        raise RuntimeError('Hermes runtime is not available.')

    resolved_model = (
        str(model or '').strip()
        or str(session_payload.get('model') or '').strip()
        or _get_default_hermes_model()
    )
    if not resolved_model or resolved_model == 'unknown':
        raise ValueError('Hermes model is not configured.')

    workspace_path = (
        str(Path(workspace).expanduser().resolve()) if workspace else _get_default_hermes_workspace_path()
    )
    state_db_path = runtime.get('state_db_path') or str(Path(runtime['active_home']) / 'state.db')

    return {
        'runtime': runtime,
        'target_id': normalized_target_id,
        'session_payload': session_payload,
        'normalized_session_id': normalized_session_id,
        'normalized_message': _build_hermes_message_with_attachments(
            normalized_message,
            normalized_files,
        ),
        'raw_message': normalized_message,
        'files': normalized_files,
        'agent_dir': agent_dir,
        'python_path': python_path,
        'resolved_model': resolved_model,
        'workspace_path': workspace_path,
        'state_db_path': state_db_path,
    }


def build_hermes_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    runtime = context.get('runtime') or {}
    session_payload = context.get('session_payload') or {}

    normalized_target_id = normalize_hermes_target_id(
        context.get('target_id') or runtime.get('target_id')
    )
    workspace_path = str(context.get('workspace_path') or '').strip()
    resolved_model = str(context.get('resolved_model') or '').strip()
    session_model = str(session_payload.get('model') or '').strip()
    profile_model = str(_get_default_hermes_model() or '').strip()

    if session_model and resolved_model and session_model == resolved_model:
        model_source = 'session'
    elif profile_model and resolved_model and profile_model == resolved_model:
        model_source = 'profile'
    else:
        model_source = 'session_or_profile'

    return {
        'target_id': normalized_target_id,
        'active_profile': str(runtime.get('active_profile') or '').strip(),
        'workspace_path': workspace_path,
        'attached_file_count': len(context.get('files') or []),
        'model': resolved_model,
        'model_source': model_source,
        'session_id': str(
            context.get('normalized_session_id') or session_payload.get('session_id') or ''
        ).strip(),
    }


def _parse_hermes_runner_result(stdout: str) -> dict[str, Any]:
    for line in reversed((stdout or '').splitlines()):
        if line.startswith(HERMES_RUNNER_RESULT_SENTINEL):
            return json.loads(line[len(HERMES_RUNNER_RESULT_SENTINEL) :])
    raise RuntimeError('Hermes runner did not return a result payload.')


def _parse_hermes_runner_event(line: str) -> dict[str, Any] | None:
    if not line.startswith(HERMES_RUNNER_EVENT_SENTINEL):
        return None
    return json.loads(line[len(HERMES_RUNNER_EVENT_SENTINEL) :])


def _build_hermes_runner_payload(context: dict[str, Any], *, emit_events: bool = False) -> dict[str, Any]:
    return {
        'agent_dir': context['agent_dir'],
        'state_db_path': context['state_db_path'],
        'session_id': context['normalized_session_id'],
        'message': context['normalized_message'],
        'messages': context['session_payload'].get('messages') or [],
        'model': context['resolved_model'],
        'workspace': context['workspace_path'],
        'context_summary': build_hermes_context_summary(context),
        'emit_events': emit_events,
    }


def _build_hermes_runner_env(context: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['HERMES_HOME'] = context['runtime']['active_home']
    env['TERMINAL_CWD'] = context['workspace_path']
    env['HERMES_SESSION_KEY'] = context['normalized_session_id']
    env['PYTHONPATH'] = (
        str(context['agent_dir'])
        if not env.get('PYTHONPATH')
        else f'{context["agent_dir"]}{os.pathsep}{env["PYTHONPATH"]}'
    )
    return env


def _build_hermes_runner_script() -> str:
    return r'''
import json
import os
import sys
import threading
import traceback
from pathlib import Path

RESULT_SENTINEL = "__OPEN_WEBUI_HERMES_RESULT__"
EVENT_SENTINEL = "__OPEN_WEBUI_HERMES_EVENT__"
API_SAFE_MSG_KEYS = {'role', 'content', 'tool_calls', 'tool_call_id', 'name', 'refusal'}


def sanitize_messages(messages):
    clean = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        sanitized = {k: v for k, v in msg.items() if k in API_SAFE_MSG_KEYS}
        if sanitized.get('role'):
            clean.append(sanitized)
    return clean


payload_line = sys.stdin.readline()
if not payload_line:
    raise RuntimeError('Hermes runner did not receive a payload.')

payload = json.loads(payload_line)
agent_dir = payload['agent_dir']
sys.path.insert(0, agent_dir)


def emit_event(event_name, data):
    if not payload.get('emit_events'):
        return
    print(EVENT_SENTINEL + json.dumps({'event': event_name, 'data': data}, ensure_ascii=False), flush=True)


def on_token(text):
    if text is None:
        return
    emit_event('token', {'text': text})


def on_tool(*cb_args, **_cb_kwargs):
    event_type = 'tool.started'
    name = ''
    preview = ''
    args = {}

    if len(cb_args) >= 4:
        event_type, name, preview, args = cb_args[:4]
    elif len(cb_args) >= 3:
        name, preview, args = cb_args[:3]
    elif len(cb_args) == 2:
        event_type, preview = cb_args[:2]
        if event_type in ('_thinking', 'reasoning.available'):
            return
        name = event_type
    else:
        return

    args_snap = {}
    if isinstance(args, dict):
        for k, v in list(args.items())[:4]:
            s2 = str(v)
            args_snap[k] = s2[:120] + ('...' if len(s2) > 120 else '')

    normalized_event = event_type if event_type else 'tool'
    emit_event(
        normalized_event,
        {
            'event': normalized_event,
            'name': name,
            'preview': preview,
            'args': args_snap,
        },
    )

    try:
        from tools.approval import has_pending as _has_pending, _pending, _lock
        if _has_pending(payload['session_id']):
            with _lock:
                pending = dict(_pending.get(payload['session_id'], {}))
            if pending:
                emit_event('approval.pending', pending)
    except Exception:
        pass


try:
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from tools.approval import register_gateway_notify, resolve_gateway_approval, unregister_gateway_notify

    session_id = payload['session_id']
    workspace = payload['workspace']
    model = payload['model']
    message = payload['message']

    os.environ['TERMINAL_CWD'] = workspace
    os.environ['HERMES_SESSION_KEY'] = session_id
    if payload.get('emit_events'):
        os.environ['HERMES_GATEWAY_SESSION'] = '1'
    else:
        os.environ['HERMES_EXEC_ASK'] = '1'

    db = SessionDB(Path(payload['state_db_path']))
    db.ensure_session(session_id, source='open_webui', model=model)
    history = db.get_messages_as_conversation(session_id) or sanitize_messages(payload.get('messages'))
    runtime = resolve_runtime_provider()

    agent = AIAgent(
        model=model,
        provider=runtime.get('provider'),
        base_url=runtime.get('base_url'),
        api_key=runtime.get('api_key'),
        credential_pool=runtime.get('credential_pool'),
        platform='open_webui',
        quiet_mode=True,
        session_id=session_id,
        session_db=db,
        stream_delta_callback=on_token if payload.get('emit_events') else None,
        tool_progress_callback=on_tool if payload.get('emit_events') else None,
    )

    workspace_system_msg = (
        f"Active workspace at session start: {workspace}\n"
        "Every user message is prefixed with [Workspace: /absolute/path] indicating the "
        "workspace the user has selected in the web UI at the time they sent that message. "
        "This tag is the single authoritative source of the active workspace and updates "
        "with every message. It overrides any prior workspace mentioned in this system "
        "prompt, memory, or conversation history. Always use the value from the most recent "
        "[Workspace: ...] tag as your default working directory for ALL file operations."
    )

    control_thread = None

    if payload.get('emit_events'):
        def notify_approval(approval_data):
            emit_event('approval.pending', approval_data)

        def control_loop():
            while True:
                raw = sys.stdin.readline()
                if raw == '':
                    return

                raw = raw.strip()
                if not raw:
                    continue

                request_id = None

                try:
                    control_payload = json.loads(raw)
                    request_id = control_payload.get('request_id')
                except Exception as exc:
                    emit_event(
                        'approval.error',
                        {
                            'request_id': request_id,
                            'message': f'Invalid Hermes control payload: {exc}',
                        },
                    )
                    continue

                if control_payload.get('action') != 'approval.resolve':
                    continue

                choice = str(control_payload.get('choice') or 'deny')
                resolve_all = bool(control_payload.get('resolve_all', False))
                resolved_count = resolve_gateway_approval(
                    session_id,
                    choice,
                    resolve_all=resolve_all,
                )

                if resolved_count <= 0:
                    emit_event(
                        'approval.error',
                        {
                            'request_id': request_id,
                            'session_id': session_id,
                            'message': 'No pending Hermes approval found.',
                        },
                    )
                    continue

                emit_event(
                    'approval.resolved',
                    {
                        'request_id': request_id,
                        'session_id': session_id,
                        'choice': choice,
                        'resolved_count': resolved_count,
                    },
                )

        register_gateway_notify(session_id, notify_approval)
        control_thread = threading.Thread(
            target=control_loop,
            daemon=True,
            name=f'hermes-approval-control-{session_id[:8]}',
        )
        control_thread.start()

    emit_event('run.started', {'session_id': session_id})

    try:
        result = agent.run_conversation(
            user_message=f"[Workspace: {workspace}]\n{message}",
            system_message=workspace_system_msg,
            conversation_history=history,
            task_id=session_id,
            persist_user_message=message,
        )
    finally:
        if payload.get('emit_events'):
            unregister_gateway_notify(session_id)

    print(RESULT_SENTINEL + json.dumps({
        'session_id': getattr(agent, 'session_id', session_id) or session_id,
        'answer': result.get('final_response') or '',
        'result': {k: v for k, v in result.items() if k != 'messages'},
    }, ensure_ascii=False), flush=True)
except Exception as exc:
    print(RESULT_SENTINEL + json.dumps({
        'error': str(exc),
        'error_type': type(exc).__name__,
        'traceback': traceback.format_exc(),
    }, ensure_ascii=False), flush=True)
    '''.replace('__OPEN_WEBUI_HERMES_RESULT__', HERMES_RUNNER_RESULT_SENTINEL).replace(
        '__OPEN_WEBUI_HERMES_EVENT__',
        HERMES_RUNNER_EVENT_SENTINEL,
    )


def _build_hermes_session_message_result(
    context: dict[str, Any],
    runner_result: dict[str, Any],
) -> dict[str, Any]:
    updated_session_id = str(runner_result.get('session_id') or context['normalized_session_id'])
    updated_session = load_hermes_session(
        updated_session_id,
        target_id=context.get('target_id'),
    )
    if not updated_session:
        updated_session = {
            **context['session_payload'],
            'session_id': updated_session_id,
            'target_id': normalize_hermes_target_id(
                context.get('target_id') or context['session_payload'].get('target_id')
            ),
            'runtime_target_id': normalize_hermes_target_id(
                context.get('target_id') or context['session_payload'].get('runtime_target_id')
            ),
            'messages': runner_result.get('messages')
            or context['session_payload'].get('messages')
            or [],
            'updated_at': int(time.time()),
        }

    return {
        'session_id': updated_session_id,
        'target_id': normalize_hermes_target_id(
            updated_session.get('runtime_target_id') or updated_session.get('target_id')
        ),
        'answer': runner_result.get('answer') or '',
        'session': updated_session,
        'chat_payload': build_chat_import_payload(updated_session),
        'result': runner_result.get('result') or {},
        'context_summary': build_hermes_context_summary(
            {
                **context,
                'session_payload': updated_session,
                'normalized_session_id': updated_session_id,
            }
        ),
    }


def start_hermes_session_message_process(
    session_id: str | None,
    message: str,
    *,
    model: str | None = None,
    workspace: str | None = None,
    emit_events: bool = False,
    target_id: str | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = _resolve_hermes_send_context(
        session_id,
        message,
        model=model,
        workspace=workspace,
        target_id=target_id,
        files=files,
    )
    process = subprocess.Popen(
        [context['python_path'], '-c', _build_hermes_runner_script()],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=context['agent_dir'],
        env=_build_hermes_runner_env(context),
        bufsize=1,
    )

    if process.stdin is None:
        process.kill()
        raise RuntimeError('Hermes runner stdin is not available.')

    process.stdin.write(
        json.dumps(_build_hermes_runner_payload(context, emit_events=emit_events)) + '\n'
    )
    process.stdin.flush()

    if not emit_events:
        process.stdin.close()

    return {
        'context': context,
        'process': process,
    }


def send_hermes_runner_control_message(process: Any, payload: dict[str, Any]) -> None:
    stdin = getattr(process, 'stdin', None)
    if stdin is None:
        raise RuntimeError('Hermes runner stdin is not available.')

    stdin.write(json.dumps(payload) + '\n')
    stdin.flush()


def send_hermes_session_message(
    session_id: str | None,
    message: str,
    *,
    model: str | None = None,
    workspace: str | None = None,
    timeout_seconds: int = HERMES_SEND_TIMEOUT_SECONDS,
    target_id: str | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    runner = start_hermes_session_message_process(
        session_id,
        message,
        model=model,
        workspace=workspace,
        emit_events=False,
        target_id=target_id,
        files=files,
    )
    process = runner['process']
    context = runner['context']

    stdin = getattr(process, 'stdin', None)
    if stdin is not None and getattr(stdin, 'closed', False):
        process.stdin = None

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        raise TimeoutError('Hermes session message timed out.') from exc

    runner_result = _parse_hermes_runner_result(stdout)
    if runner_result.get('error'):
        log.error('Hermes runner failed: %s', runner_result.get('traceback') or runner_result)
        raise RuntimeError(runner_result['error'])
    if process.returncode != 0:
        raise RuntimeError((stderr or '').strip() or 'Hermes runner failed.')

    return _build_hermes_session_message_result(context, runner_result)
