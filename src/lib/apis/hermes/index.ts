import { WEBUI_API_BASE_URL } from '$lib/constants';
import { getTimeRange } from '$lib/utils';
import { EventSourceParserStream } from 'eventsource-parser/stream';

export const HERMES_DEFAULT_TARGET_ID = 'local';

export type HermesRuntime = {
	target_id: string;
	active_home: string;
	active_profile: string;
	agent_dir?: string | null;
	python_path: string;
	state_db_path: string;
	session_dir: string;
	warnings?: string[];
};

export type HermesSession = {
	target_id: string;
	session_id: string;
	title: string;
	model?: string | null;
	message_count: number;
	created_at?: number | null;
	updated_at?: number | null;
	profile?: string | null;
	source_tag?: string | null;
	last_user_content?: string | null;
	available_sources: string[];
	imported_chat_id?: string | null;
	imported_chat_archived?: boolean;
	is_auxiliary_cli_session?: boolean;
	time_range?: string;
};

export type HermesSessionsResponse = {
	target_id: string;
	active_home: string;
	active_profile: string;
	items: HermesSession[];
};

export type HermesWorkspace = {
	path: string;
	name: string;
	is_active: boolean;
};

export type HermesWorkspacesResponse = {
	target_id: string;
	active_home: string;
	active_profile: string;
	last_workspace?: string | null;
	items: HermesWorkspace[];
};

export type HermesWorkspaceSwitchResponse = HermesWorkspacesResponse;

export type HermesWorkspaceBrowseEntry = {
	name: string;
	type: 'file' | 'directory';
	size?: number | null;
	modified?: number | null;
};

export type HermesWorkspaceBrowseResponse = {
	target_id: string;
	active_home: string;
	active_profile: string;
	root_path: string;
	current_path: string;
	entries: HermesWorkspaceBrowseEntry[];
};

export type HermesProfile = {
	name: string;
	path: string;
	is_default: boolean;
	is_active: boolean;
	model?: string | null;
	provider?: string | null;
	has_env: boolean;
	has_soul: boolean;
	has_memory: boolean;
	has_user_profile: boolean;
	memory_enabled: boolean;
	user_profile_enabled: boolean;
	gateway_running: boolean;
	skill_count: number;
};

export type HermesProfilesResponse = {
	target_id: string;
	active_home: string;
	active_profile: string;
	items: HermesProfile[];
};

export type HermesProfileSwitchResponse = HermesProfilesResponse & {
	default_model?: string | null;
	default_workspace?: string | null;
};

export type HermesImportResponse = {
	target_id: string;
	session_id: string;
	already_imported?: boolean;
	chat: {
		id: string;
		title: string;
		created_at: number;
		updated_at: number;
	};
};

export type HermesSendRequest = {
	session_id?: string | null;
	message: string;
	model?: string | null;
	workspace?: string | null;
	client_request_id?: string | null;
	target_id?: string | null;
	files?: Record<string, any>[] | null;
};

export type HermesSendResponse = {
	target_id: string;
	session_id: string;
	answer?: string;
	chat: Record<string, any>;
	meta?: Record<string, any>;
	result?: Record<string, any>;
	context_summary?: Record<string, any> | null;
};

export type HermesStreamStartResponse = {
	target_id: string;
	stream_id: string;
	session_id: string;
	status: string;
};

export type HermesStreamStatusResponse = {
	target_id: string;
	stream_id: string;
	session_id: string;
	status: string;
	done: boolean;
	error?: string | null;
	result?: HermesSendResponse | null;
	context_summary?: Record<string, any> | null;
	approval_pending?: Record<string, any> | null;
	started_at: number;
	updated_at: number;
};

export type HermesApprovalResolution = 'once' | 'session' | 'always' | 'deny';

export type HermesSessionApprovalRequest = {
	stream_id: string;
	choice: HermesApprovalResolution;
	target_id?: string | null;
};

export type HermesSessionApprovalResponse = {
	target_id: string;
	stream_id: string;
	session_id: string;
	status: string;
	choice: HermesApprovalResolution;
	request_id: string;
};

export type HermesStreamEvent = {
	event: string;
	data: Record<string, any>;
};

const createHermesEventStream = async (
	responseBody: ReadableStream<Uint8Array>
): Promise<AsyncGenerator<HermesStreamEvent>> => {
	const reader = responseBody
		.pipeThrough(new TextDecoderStream())
		.pipeThrough(new EventSourceParserStream())
		.getReader();

	return (async function* () {
		while (true) {
			const { value, done } = await reader.read();
			if (done) {
				return;
			}

			if (!value?.data) {
				continue;
			}

			try {
				yield {
					event: value.event || 'message',
					data: JSON.parse(value.data)
				};
			} catch (error) {
				console.error('Error parsing Hermes SSE event:', error);
			}
		}
	})();
};

export const getHermesRuntime = async (token: string): Promise<HermesRuntime> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/runtime`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getHermesSessions = async (token: string): Promise<HermesSessionsResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/sessions`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return {
		...res,
		items: (res?.items ?? []).map((item) => ({
			...item,
			time_range: item.updated_at ? getTimeRange(item.updated_at) : ''
		}))
	};
};

export const getHermesWorkspaces = async (token: string): Promise<HermesWorkspacesResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/workspaces`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const switchHermesWorkspace = async (
	token: string,
	path: string
): Promise<HermesWorkspaceSwitchResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/workspaces/switch`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ path })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getHermesWorkspaceBrowse = async (
	token: string,
	path?: string | null
): Promise<HermesWorkspaceBrowseResponse> => {
	let error = null;
	const query = path ? `?path=${encodeURIComponent(path)}` : '';

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/workspaces/browse${query}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getHermesWorkspaceFileUrl = (path: string) =>
	`${WEBUI_API_BASE_URL}/hermes/workspaces/file?path=${encodeURIComponent(path)}`;

export const getHermesProfiles = async (token: string): Promise<HermesProfilesResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/profiles`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const switchHermesProfile = async (
	token: string,
	name: string
): Promise<HermesProfileSwitchResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/profiles/switch`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({ name })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const importHermesSession = async (
	token: string,
	sessionId: string,
	targetId?: string | null
): Promise<HermesImportResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/sessions/import`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			session_id: sessionId,
			target_id: targetId ?? null
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const sendHermesSessionMessage = async (
	token: string,
	payload: HermesSendRequest
): Promise<HermesSendResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/sessions/send`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const startHermesSessionMessageStream = async (
	token: string,
	payload: HermesSendRequest
): Promise<HermesStreamStartResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/sessions/start`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getHermesSessionMessageStream = async (
	token: string,
	streamId: string
): Promise<AsyncGenerator<HermesStreamEvent>> => {
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/hermes/sessions/stream?stream_id=${encodeURIComponent(streamId)}`,
		{
			method: 'GET',
			headers: {
				Accept: 'text/event-stream',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	);

	if (!res.ok) {
		const error = await res.json().catch(() => null);
		throw error?.detail ?? error ?? 'Failed to open Hermes stream.';
	}

	if (!res.body) {
		throw 'Hermes stream response body is empty.';
	}

	return createHermesEventStream(res.body);
};

export const getHermesSessionMessageStreamStatus = async (
	token: string,
	streamId: string
): Promise<HermesStreamStatusResponse> => {
	let error = null;

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/hermes/sessions/stream/status?stream_id=${encodeURIComponent(streamId)}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const respondHermesSessionApproval = async (
	token: string,
	payload: HermesSessionApprovalRequest
): Promise<HermesSessionApprovalResponse> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/hermes/sessions/approval`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const cancelHermesSessionMessageStream = async (
	token: string,
	streamId: string
): Promise<HermesStreamStatusResponse> => {
	let error = null;

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/hermes/sessions/cancel?stream_id=${encodeURIComponent(streamId)}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
