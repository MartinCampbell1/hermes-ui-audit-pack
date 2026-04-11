export const getHermesStatusEntries = (message: any): any[] => {
	if (Array.isArray(message?.statusHistory)) {
		return message.statusHistory;
	}

	return message?.status ? [message.status] : [];
};

const HERMES_TOOL_STATUS_ACTION = 'hermes_tool';
const LIVE_HERMES_TOOL_EXECUTION_PREFIX = 'hermes-live-tool-';

const TOOL_PREFIX_PATTERN = /^\[Tool:\s*([^\]]+)\]\s*/i;

const TOOL_RESULT_KEYS = [
	'content',
	'error',
	'exitCode',
	'exit_code',
	'files',
	'matches',
	'message',
	'mode',
	'output',
	'query',
	'result',
	'results',
	'stderr',
	'stdout',
	'success',
	'summary',
	'total_count'
];

const HERMES_TOOL_SUMMARY_MAX_LENGTH = 120;

const getFirstNonEmptyLine = (value: string) =>
	value
		.split(/\r?\n/)
		.map((line) => line.trim())
		.find(Boolean) || '';

const clipHermesSummary = (value: string, maxLength = HERMES_TOOL_SUMMARY_MAX_LENGTH) => {
	if (!value || value.length <= maxLength) {
		return value;
	}

	return `${value.slice(0, maxLength - 1).trimEnd()}…`;
};

const toToolSummaryText = (value: unknown): string => {
	if (typeof value === 'string') {
		return value.trim();
	}

	if (typeof value === 'number' || typeof value === 'boolean') {
		return String(value);
	}

	return '';
};

const normalizeHermesTimestamp = (value: unknown) => {
	const numericValue = getNumericPayloadValue(value);
	if (numericValue === null) {
		return null;
	}

	return numericValue > 1e12 ? numericValue : numericValue * 1000;
};

const getHermesExecutionPayload = (execution: any): Record<string, unknown> => {
	if (!execution || typeof execution !== 'object') {
		return {};
	}

	const resultPayload =
		execution?.result && typeof execution.result === 'object' && !Array.isArray(execution.result)
			? execution.result
			: null;

	return {
		...execution,
		...(resultPayload ?? {})
	};
};

const getHermesDurationMs = (payload: Record<string, unknown>) => {
	const directDuration = [
		payload.duration_ms,
		payload.durationMs,
		payload.elapsed_ms,
		payload.elapsedMs,
		payload.runtime_ms,
		payload.runtimeMs
	]
		.map(getNumericPayloadValue)
		.find((value) => value !== null);

	if (directDuration !== undefined && directDuration !== null) {
		return directDuration;
	}

	const startedAt = normalizeHermesTimestamp(
		payload.started_at ?? payload.startedAt ?? payload.start_time ?? payload.startedTime
	);
	const updatedAt = normalizeHermesTimestamp(
		payload.updated_at ?? payload.updatedAt ?? payload.completed_at ?? payload.completedAt
	);
	const endedAt = normalizeHermesTimestamp(payload.ended_at ?? payload.endedAt ?? payload.end_time);

	if (startedAt === null) {
		return null;
	}

	const endAt = updatedAt ?? endedAt;
	if (endAt !== null && endAt >= startedAt) {
		return endAt - startedAt;
	}

	if (payload.done === false || payload.state === 'running') {
		return Math.max(0, Date.now() - startedAt);
	}

	return null;
};

const formatHermesDuration = (durationMs: number) => {
	if (!Number.isFinite(durationMs) || durationMs <= 0) {
		return '';
	}

	if (durationMs < 1000) {
		return `${Math.max(1, Math.round(durationMs))}ms`;
	}

	const durationSeconds = durationMs / 1000;
	if (durationSeconds < 10) {
		return `${durationSeconds.toFixed(1)}s`;
	}

	if (durationSeconds < 60) {
		return `${Math.round(durationSeconds)}s`;
	}

	const durationMinutes = durationSeconds / 60;
	if (durationMinutes < 10) {
		return `${durationMinutes.toFixed(1)}m`;
	}

	if (durationMinutes < 60) {
		return `${Math.round(durationMinutes)}m`;
	}

	return `${(durationMinutes / 60).toFixed(1)}h`;
};

const getHermesOutputDestinationLabel = (payload: Record<string, unknown>) => {
	const fileCount = getCollectionCount(payload, 'files');
	if (fileCount !== null && fileCount > 0) {
		return 'workspace';
	}

	const workspacePath =
		getFirstNonEmptyLine(
			toToolSummaryText(
				payload.workspace ??
					payload.workspace_path ??
					payload.workspacePath ??
					payload.target ??
					payload.target_path ??
					payload.targetPath ??
					payload.directory ??
					payload.path
			)
		) || '';
	if (workspacePath) {
		return clipHermesSummary(`workspace: ${workspacePath}`);
	}

	if (getFirstNonEmptyLine(toToolSummaryText(payload.stdout))) {
		return 'stdout';
	}

	if (getFirstNonEmptyLine(toToolSummaryText(payload.stderr))) {
		return 'stderr';
	}

	if (
		getFirstNonEmptyLine(toToolSummaryText(payload.output)) ||
		getFirstNonEmptyLine(toToolSummaryText(payload.content)) ||
		getFirstNonEmptyLine(toToolSummaryText(payload.result))
	) {
		return 'inline output';
	}

	return '';
};

const getHermesOutputCountLabel = (payload: Record<string, unknown>) => {
	const filesCount = getCollectionCount(payload, 'files');
	if (filesCount !== null && filesCount > 0) {
		return getCountLabel(filesCount, 'file', 'files');
	}

	const resultsCount = getCollectionCount(payload, 'results');
	if (resultsCount !== null && resultsCount > 0) {
		return getCountLabel(resultsCount, 'result', 'results');
	}

	const matchesCount = getCollectionCount(payload, 'matches');
	if (matchesCount !== null && matchesCount > 0) {
		return getCountLabel(matchesCount, 'match', 'matches');
	}

	return '';
};

const getHermesTimingLabel = (payload: Record<string, unknown>) => {
	const durationMs = getHermesDurationMs(payload);
	return durationMs !== null ? formatHermesDuration(durationMs) : '';
};

const getHermesPayloadTrustMeta = (payload: Record<string, unknown>) => {
	const pieces = [
		getHermesOutputDestinationLabel(payload),
		getHermesOutputCountLabel(payload),
		getHermesTimingLabel(payload)
	].filter(Boolean);

	return pieces.join(' • ');
};

const getHermesSurfaceSummaryText = (
	payload: Record<string, unknown>,
	{
		fallback,
		state
	}: {
		fallback: string;
		state?: 'running' | 'done' | 'failed' | 'idle';
	}
) => {
	const stateName = state ?? 'idle';
	const exitCode = getExitCode(payload);
	const errorSummary = getFirstNonEmptyLine(
		toToolSummaryText(payload.error) || toToolSummaryText(payload.stderr)
	);

	if (errorSummary && (stateName === 'failed' || exitCode === null || exitCode !== 0)) {
		return clipHermesSummary(errorSummary);
	}

	for (const key of ['summary', 'message', 'output', 'stdout', 'result', 'content', 'stderr']) {
		const summary = getFirstNonEmptyLine(toToolSummaryText(payload[key]));
		if (summary) {
			return clipHermesSummary(summary);
		}
	}

	const collectionSummary = getCollectionSummary(payload);
	if (collectionSummary) {
		if (getCollectionCount(payload, 'files') !== null) {
			return clipHermesSummary(`Generated ${collectionSummary}`);
		}

		if (getCollectionCount(payload, 'matches') !== null) {
			return clipHermesSummary(`Found ${collectionSummary}`);
		}

		const resultsCount = getCollectionCount(payload, 'results');
		const query = getFirstNonEmptyLine(toToolSummaryText(payload.query));
		const mode = getFirstNonEmptyLine(toToolSummaryText(payload.mode));
		if (resultsCount !== null && !query && !mode) {
			return clipHermesSummary(`Returned ${collectionSummary}`);
		}

		return clipHermesSummary(collectionSummary);
	}

	if (typeof payload.success === 'boolean') {
		return payload.success ? 'Success' : 'Failed';
	}

	if (exitCode !== null && exitCode !== 0) {
		return `exit code: ${exitCode}`;
	}

	if (stateName === 'running') {
		const preview = getFirstNonEmptyLine(
			toToolSummaryText(payload.preview) ||
				toToolSummaryText(payload.command) ||
				toToolSummaryText(payload.message)
		);

		if (preview) {
			return clipHermesSummary(preview);
		}

		return 'Running';
	}

	return fallback;
};

const getHermesToolEventName = (toolEvent: any) => {
	if (typeof toolEvent?.name === 'string' && toolEvent.name.trim()) {
		return toolEvent.name.trim();
	}

	if (typeof toolEvent?.tool_name === 'string' && toolEvent.tool_name.trim()) {
		return toolEvent.tool_name.trim();
	}

	return 'Tool activity';
};

const getHermesToolEventPreview = (toolEvent: any) =>
	getFirstNonEmptyLine(
		toToolSummaryText(toolEvent?.preview) ||
			toToolSummaryText(toolEvent?.message) ||
			toToolSummaryText(toolEvent?.command)
	);

const buildSyntheticHermesToolExecutionId = (executions: any[]) =>
	`${LIVE_HERMES_TOOL_EXECUTION_PREFIX}${executions.length + 1}`;

const getNumericPayloadValue = (value: unknown) => {
	if (typeof value === 'number' && Number.isFinite(value)) {
		return value;
	}

	if (typeof value === 'string' && value.trim()) {
		const parsed = Number(value);
		return Number.isFinite(parsed) ? parsed : null;
	}

	return null;
};

const getExitCode = (payload: Record<string, unknown>) =>
	getNumericPayloadValue(payload.exit_code ?? payload.exitCode);

const getCountLabel = (count: number, singular: string, plural: string) =>
	`${count} ${count === 1 ? singular : plural}`;

const getCollectionCount = (payload: Record<string, unknown>, key: string) => {
	const value = payload[key];
	if (Array.isArray(value)) {
		const totalCount = getNumericPayloadValue(payload.total_count);
		return totalCount !== null ? totalCount : value.length;
	}

	if (typeof value !== 'undefined') {
		return getNumericPayloadValue(value);
	}

	if (
		key === 'results' &&
		!Object.prototype.hasOwnProperty.call(payload, 'files') &&
		!Object.prototype.hasOwnProperty.call(payload, 'matches')
	) {
		return getNumericPayloadValue(payload.total_count);
	}

	return null;
};

const getCollectionSummary = (payload: Record<string, unknown>) => {
	for (const [key, singular, plural] of [
		['files', 'file', 'files'],
		['matches', 'match', 'matches']
	]) {
		if (!Object.prototype.hasOwnProperty.call(payload, key)) {
			continue;
		}

		const count = getCollectionCount(payload, key);
		if (count !== null) {
			return getCountLabel(count, singular, plural);
		}
	}

	const resultsCount = getCollectionCount(payload, 'results');
	const query = getFirstNonEmptyLine(toToolSummaryText(payload.query));
	const mode = getFirstNonEmptyLine(toToolSummaryText(payload.mode));

	if (resultsCount !== null) {
		const countLabel = getCountLabel(resultsCount, 'result', 'results');
		if (query) {
			return `query: ${query} (${countLabel})`;
		}
		if (mode) {
			return `mode: ${mode} (${countLabel})`;
		}

		return countLabel;
	}

	if (query) {
		return `query: ${query}`;
	}

	if (mode) {
		return `mode: ${mode}`;
	}

	const totalCount = getNumericPayloadValue(payload.total_count);
	return totalCount !== null ? getCountLabel(totalCount, 'result', 'results') : null;
};

export const getHermesApprovalSummary = (approval: any) => {
	if (!approval) {
		return '';
	}

	if (approval?.state === 'resolved') {
		if (approval?.resolution === 'once') {
			return 'Approved once';
		}

		if (approval?.resolution === 'session') {
			return 'Approved for this session';
		}

		if (approval?.resolution === 'always') {
			return 'Approved permanently';
		}

		if (approval?.resolution === 'deny') {
			return 'Denied';
		}

		return 'Approval resolved';
	}

	return 'Approval pending';
};

export const getHermesToolExecutionSurfaceSummary = (
	execution: any,
	fallback = 'Completed'
): { summary: string; meta: string } => {
	const payload = getHermesExecutionPayload(execution);
	const state = getHermesToolExecutionState(execution);

	return {
		summary: getHermesSurfaceSummaryText(payload, { fallback, state }),
		meta: getHermesPayloadTrustMeta(payload)
	};
};

const getHermesImportedToolJsonSummary = (
	detail: string,
	fallback: string,
	toolName = ''
) => {
	let parsed: unknown;

	try {
		parsed = JSON.parse(detail);
	} catch {
		return null;
	}

	if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
		return null;
	}

	const payload = parsed as Record<string, unknown>;
	const normalizedToolName = toolName.trim().toLowerCase();
	const hasKnownResultShape = TOOL_RESULT_KEYS.some((key) =>
		Object.prototype.hasOwnProperty.call(payload, key)
	);

	if (!hasKnownResultShape) {
		return null;
	}

	const exitCode = getExitCode(payload);
	const errorSummary = getFirstNonEmptyLine(
		toToolSummaryText(payload.error) || toToolSummaryText(payload.stderr)
	);

	if (errorSummary && (exitCode === null || exitCode !== 0)) {
		return errorSummary;
	}

	for (const key of ['summary', 'message', 'output', 'stdout', 'result', 'content', 'stderr']) {
		const summary = getFirstNonEmptyLine(toToolSummaryText(payload[key]));
		if (summary) {
			if (
				typeof payload.success === 'boolean' &&
				payload.success &&
				['ok', 'okay', 'success', 'done', 'completed'].includes(summary.toLowerCase())
			) {
				continue;
			}

			return summary;
		}
	}

	const collectionSummary = getCollectionSummary(payload);
	if (collectionSummary) {
		if (getCollectionCount(payload, 'files') !== null) {
			if (
				['find', 'glob', 'grep', 'list', 'ls', 'read_dir', 'search'].includes(normalizedToolName)
			) {
				return `Found ${collectionSummary}`;
			}

			return `Generated ${collectionSummary}`;
		}

		if (getCollectionCount(payload, 'matches') !== null) {
			return `Found ${collectionSummary}`;
		}

		const resultsCount = getCollectionCount(payload, 'results');
		const query = getFirstNonEmptyLine(toToolSummaryText(payload.query));
		const mode = getFirstNonEmptyLine(toToolSummaryText(payload.mode));
		if (resultsCount !== null && !query && !mode) {
			return `Returned ${collectionSummary}`;
		}

		return collectionSummary;
	}

	if (typeof payload.success === 'boolean') {
		return payload.success ? 'Success' : 'Failed';
	}

	if (exitCode !== null && exitCode !== 0) {
		return `exit code: ${exitCode}`;
	}

	return fallback;
};

export const getHermesImportedToolSurfaceSummary = (
	message: any,
	fallback = 'Completed'
): { summary: string; meta: string } => {
	const detail = getHermesImportedToolContent(message);
	if (!detail) {
		return {
			summary: fallback,
			meta: ''
		};
	}

	let parsed: unknown;

	try {
		parsed = JSON.parse(detail);
	} catch {
		return {
			summary: clipHermesSummary(getFirstNonEmptyLine(detail) || fallback),
			meta: ''
		};
	}

	if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
		return {
			summary: clipHermesSummary(getFirstNonEmptyLine(detail) || fallback),
			meta: ''
		};
	}

	const payload = parsed as Record<string, unknown>;
	const hasKnownResultShape = TOOL_RESULT_KEYS.some((key) =>
		Object.prototype.hasOwnProperty.call(payload, key)
	);

	if (!hasKnownResultShape) {
		return {
			summary: clipHermesSummary(getFirstNonEmptyLine(detail) || fallback),
			meta: ''
		};
	}

	return {
		summary: clipHermesSummary(
			getHermesImportedToolJsonSummary(detail, fallback, getHermesImportedToolName(message)) ||
				fallback
		),
		meta: getHermesPayloadTrustMeta(payload)
	};
};

export const getHermesVisibleStatusEntries = (message: any): any[] => {
	const statusEntries = getHermesStatusEntries(message);

	if ((message?.code_executions?.length ?? 0) === 0) {
		return statusEntries;
	}

	return statusEntries.filter((entry) => entry?.action !== HERMES_TOOL_STATUS_ACTION);
};

export const normalizeHermesStreamEventName = (eventName: unknown) => {
	const normalized = typeof eventName === 'string' ? eventName.trim().toLowerCase() : '';

	if (!normalized || normalized === 'message') {
		return 'message';
	}

	if (
		normalized === 'approval.pending' ||
		normalized === 'approval'
	) {
		return 'approval';
	}

	if (
		normalized === 'tool' ||
		normalized === 'tool.started' ||
		normalized === 'tool.running' ||
		normalized === 'tool.finished' ||
		normalized === 'tool.completed' ||
		normalized === 'tool.error' ||
		normalized === 'tool.failed'
	) {
		return 'tool';
	}

	if (normalized === 'done') {
		return 'done';
	}

	if (normalized === 'run.started') {
		return 'run.started';
	}

	if (normalized === 'run.completed') {
		return 'run.completed';
	}

	return normalized;
};

export const getHermesToolExecutionState = (
	toolEvent: any
): 'running' | 'done' | 'failed' => {
	const eventName =
		typeof toolEvent?.event === 'string'
			? toolEvent.event.trim().toLowerCase()
			: typeof toolEvent?.type === 'string'
				? toolEvent.type.trim().toLowerCase()
				: '';

	if (
		toolEvent?.error ||
		eventName === 'tool.error' ||
		eventName === 'tool.failed' ||
		eventName === 'failed' ||
		eventName === 'error'
	) {
		return 'failed';
	}

	if (
		toolEvent?.done === true ||
		toolEvent?.result ||
		eventName === 'tool.finished' ||
		eventName === 'tool.completed' ||
		eventName === 'done' ||
		eventName === 'completed' ||
		eventName === 'finished'
	) {
		return 'done';
	}

	return 'running';
};

export const upsertHermesToolExecution = (executions: any[] | null | undefined, toolEvent: any) => {
	const nextExecutions = Array.isArray(executions) ? [...executions] : [];
	const explicitId =
		typeof toolEvent?.id === 'string' && toolEvent.id.trim() ? toolEvent.id.trim() : null;
	const state = getHermesToolExecutionState(toolEvent);
	const name = getHermesToolEventName(toolEvent);
	const preview = getHermesToolEventPreview(toolEvent);
	const now = Date.now();

	let existingIndex = explicitId
		? nextExecutions.findIndex((execution) => execution?.id === explicitId)
		: -1;

	if (existingIndex === -1 && state !== 'running') {
		for (let index = nextExecutions.length - 1; index >= 0; index -= 1) {
			const execution = nextExecutions[index];
			if (execution?.name === name && !execution?.result) {
				existingIndex = index;
				break;
			}
		}
	}

	const baseExecution =
		existingIndex === -1
			? {
					id: explicitId || buildSyntheticHermesToolExecutionId(nextExecutions),
					started_at: now
				}
			: { ...nextExecutions[existingIndex] };

	const nextExecution = {
		...baseExecution,
		name,
		preview: preview || baseExecution.preview || '',
		message:
			toToolSummaryText(toolEvent?.message) || toToolSummaryText(baseExecution.message) || '',
		command:
			toToolSummaryText(toolEvent?.command) || toToolSummaryText(baseExecution.command) || '',
		args:
			toolEvent?.args && typeof toolEvent.args === 'object' && !Array.isArray(toolEvent.args)
				? toolEvent.args
				: baseExecution.args,
		event: typeof toolEvent?.event === 'string' ? toolEvent.event : baseExecution.event,
		started_at: baseExecution.started_at ?? now,
		updated_at: now
	};

	if (state === 'running') {
		nextExecution.result = null;
	} else if (state === 'failed') {
		nextExecution.completed_at = now;
		nextExecution.result = {
			error:
				toToolSummaryText(toolEvent?.error) ||
				preview ||
				nextExecution.message ||
				nextExecution.command ||
				'Tool failed'
		};
	} else {
		const nextResult =
			toolEvent?.result && typeof toolEvent.result === 'object'
				? { ...toolEvent.result }
				: {};

		if (toolEvent?.files && !nextResult.files) {
			nextResult.files = toolEvent.files;
		}

		if (!nextResult.output && !nextResult.message && !nextResult.content) {
			nextResult.output =
				preview || nextExecution.message || nextExecution.command || 'Completed';
		}

		nextExecution.completed_at = now;
		nextExecution.result = nextResult;
	}

	if (existingIndex === -1) {
		nextExecutions.push(nextExecution);
	} else {
		nextExecutions[existingIndex] = nextExecution;
	}

	return nextExecutions;
};

export const isHermesImportedToolMessage = (message: any) =>
	message?.role === 'tool' || message?.sourceRole === 'tool';

export const getHermesImportedToolName = (message: any) => {
	const explicitName = typeof message?.toolName === 'string' ? message.toolName.trim() : '';
	if (explicitName) {
		return explicitName;
	}

	const content = typeof message?.content === 'string' ? message.content.trim() : '';
	const match = content.match(TOOL_PREFIX_PATTERN);

	return match?.[1]?.trim() || 'tool';
};

export const getHermesImportedToolContent = (message: any) => {
	const content = typeof message?.content === 'string' ? message.content.trim() : '';

	if (!content) {
		return '';
	}

	return content.replace(TOOL_PREFIX_PATTERN, '').trim();
};

export const getHermesImportedToolSummary = (
	message: any,
	fallback = 'Completed'
): string => {
	return getHermesImportedToolSurfaceSummary(message, fallback).summary;
};

export const getCurrentBranchLatestAssistantMessageId = (history: {
	currentId?: string | null;
	messages?: Record<string, any>;
}) => {
	const messages = history?.messages ?? {};
	const seen = new Set<string>();
	let messageId = history?.currentId ?? null;

	while (messageId && !seen.has(messageId)) {
		const message = messages[messageId];
		if (!message) {
			break;
		}

		if (message.role === 'assistant') {
			return messageId;
		}

		seen.add(messageId);
		messageId = message.parentId ?? null;
	}

	return null;
};

export const getHermesComposerActivityMessageId = (
	history: {
		currentId?: string | null;
		messages?: Record<string, any>;
	},
	{
		statusUpdatesEnabled = true
	}: {
		statusUpdatesEnabled?: boolean;
	} = {}
) => {
	const messageId = getCurrentBranchLatestAssistantMessageId(history);

	if (!messageId) {
		return null;
	}

	const message = history?.messages?.[messageId];
	const statusEntries = getHermesStatusEntries(message);
	const hasVisibleStatus =
		statusUpdatesEnabled && statusEntries.length > 0 && !(statusEntries.at(-1)?.hidden ?? false);
	const hasToolActivity = (message?.code_executions?.length ?? 0) > 0;

	return hasVisibleStatus || hasToolActivity ? messageId : null;
};
