import dayjs from 'dayjs';

import { getHermesSessions } from '$lib/apis/hermes';
import { hermesRecentSessions, hermesSessionsByChatId } from '$lib/stores';
import { formatDate, getTimeRange } from '$lib/utils';

export const HERMES_DEFAULT_TARGET_ID = 'local';

export type HermesSessionListItem = {
	target_id?: string | null;
	session_id: string;
	title: string;
	model?: string | null;
	message_count?: number;
	created_at?: number | null;
	updated_at?: number | null;
	profile?: string | null;
	source_tag?: string | null;
	last_user_content?: string | null;
	available_sources?: string[];
	imported_chat_id?: string | null;
	imported_chat_archived?: boolean;
	is_auxiliary_cli_session?: boolean;
	time_range?: string | null;
};

export type HermesSessionScope = 'all' | 'imported' | 'current';
export type HermesSessionActivityLabel = {
	key: string;
	values?: {
		LOCALIZED_TIME: string;
		LOCALIZED_DATE: string;
	};
};
export type HermesChatMeta = {
	session_id?: string | null;
	model?: string | null;
	profile?: string | null;
	source_tag?: string | null;
	active_home?: string | null;
	target_id?: string | null;
	runtime_target_id?: string | null;
};
export type HermesSessionGroup = {
	label: string;
	items: HermesSessionListItem[];
};
export type HermesSessionMapByImportedChatId = Record<string, HermesSessionListItem>;
export type HermesAwareChatListItem = Record<string, any> & {
	id: string;
	title?: string | null;
	created_at?: number | null;
	updated_at?: number | null;
	time_range?: string | null;
	effective_updated_at?: number | null;
};
export type HermesLoadedChatsRefreshOptions = {
	pageSize?: number;
	importedSessionLimit?: number;
};

export type HermesContextBadgeOptions = {
	includeBaseLabel?: boolean;
	includeDefaultProfile?: boolean;
	includeCliSource?: boolean;
};
export type HermesCurrentSessionOptions = {
	currentChatId?: string | null;
	currentSessionId?: string | null;
};
export type HermesRuntimeContext = {
	active_profile?: string | null;
	active_home?: string | null;
	target_id?: string | null;
};

const normalizeSearchValue = (value: string | null | undefined) =>
	String(value ?? '')
		.toLowerCase()
		.split(/\s+/)
		.filter(Boolean)
		.join(' ');

const normalizeSessionValue = (value: string | null | undefined) => {
	if (typeof value !== 'string') {
		return null;
	}

	const normalizedValue = value.trim();

	return normalizedValue.length > 0 ? normalizedValue : null;
};

export const normalizeHermesTargetId = (value: string | null | undefined) =>
	normalizeSessionValue(value) ?? HERMES_DEFAULT_TARGET_ID;

export const getHermesTargetId = (value: Record<string, any> | string | null | undefined) => {
	if (typeof value === 'string') {
		return normalizeHermesTargetId(value);
	}

	if (value && typeof value === 'object') {
		return normalizeHermesTargetId(value.runtime_target_id ?? value.target_id);
	}

	return HERMES_DEFAULT_TARGET_ID;
};

const HERMES_SOURCE_LABELS: Record<string, string> = {
	cli: 'CLI',
	json: 'JSON',
	state_db: 'State DB',
	webui: 'WebUI'
};

const HERMES_SOURCE_LABEL_ORDER: Record<string, number> = {
	webui: 0,
	state_db: 1,
	json: 2,
	cli: 3
};
const HERMES_SOURCE_ORDER = ['cli', 'webui', 'state_db', 'json'];

const getModelTerms = (model: string | null | undefined) => {
	if (!model) {
		return [];
	}

	return [model, model.split('/').pop() ?? model];
};

const getSourceTerms = (sourceTag: string | null | undefined) => {
	const rawSourceTag = normalizeSessionValue(sourceTag);
	const formattedSourceTag = formatHermesSourceLabel(sourceTag);

	return [rawSourceTag, formattedSourceTag].filter(Boolean);
};

const getSearchHaystack = (session: HermesSessionListItem) =>
	normalizeSearchValue(
		[
			session.session_id,
			session.title,
			session.last_user_content,
			session.profile,
			...getSourceTerms(session.source_tag),
			...(session.available_sources ?? []).flatMap((sourceTag) => getSourceTerms(sourceTag)),
			...getModelTerms(session.model)
		].join(' ')
	);

export const isCurrentHermesSession = (
	session: HermesSessionListItem,
	{ currentChatId = null, currentSessionId = null }: HermesCurrentSessionOptions = {}
) => {
	const normalizedCurrentChatId = normalizeSessionValue(currentChatId);
	const normalizedCurrentSessionId = normalizeSessionValue(currentSessionId);

	if (normalizedCurrentChatId && session.imported_chat_id === normalizedCurrentChatId) {
		return true;
	}

	return (
		normalizedCurrentSessionId !== null &&
		normalizeSessionValue(session.session_id) === normalizedCurrentSessionId
	);
};

export const getHermesSessionStateLabelKey = ({
	temporaryChatEnabled = false,
	currentHermesSessionId = null,
	currentMessageId = null
}: {
	temporaryChatEnabled?: boolean;
	currentHermesSessionId?: string | null;
	currentMessageId?: string | null;
} = {}) => {
	if (temporaryChatEnabled) {
		return 'Temporary Chat';
	}

	if (normalizeSessionValue(currentHermesSessionId)) {
		return 'Active';
	}

	if (normalizeSessionValue(currentMessageId)) {
		return 'Current chat';
	}

	return '';
};

export const getHermesModelSourceLabelKey = (
	source: 'session' | 'profile' | 'fallback' | 'unknown'
) => {
	if (source === 'session') {
		return 'Pinned in session context';
	}

	if (source === 'profile') {
		return 'Inherited from active Hermes profile';
	}

	if (source === 'fallback') {
		return 'Browser fallback only';
	}

	return 'Model source unknown';
};

export const formatHermesScopedCount = (
	label: string,
	count: number | null | undefined,
	translate: (key: string, options?: Record<string, any>) => string
) => {
	if (typeof count !== 'number') {
		return '';
	}

	return `${translate(label)}: ${count}`;
};

export const getPersistedHermesSessionContext = ({
	chatHermesSession = null,
	chatMeta = null,
	runtime = null
}: {
	chatHermesSession?: Record<string, any> | null;
	chatMeta?: HermesChatMeta | null;
	runtime?: HermesRuntimeContext | null;
} = {}) => {
	const persistedSessionId = normalizeSessionValue(chatHermesSession?.session_id);
	const persistedModel = normalizeSessionValue(chatHermesSession?.model);
	const persistedProfile = normalizeSessionValue(chatHermesSession?.profile);
	const persistedHome = normalizeSessionValue(chatHermesSession?.active_home);
	const persistedTargetId = normalizeSessionValue(
		chatHermesSession?.runtime_target_id ?? chatHermesSession?.target_id
	);
	const persistedSource = normalizeSessionValue(
		chatHermesSession?.source_tag ?? chatHermesSession?.source
	);

	if (
			chatHermesSession &&
			typeof chatHermesSession === 'object' &&
			(persistedSessionId ||
				persistedModel ||
				persistedProfile ||
				persistedHome ||
				persistedSource ||
				persistedTargetId)
		) {
			return chatHermesSession;
		}

	if (chatMeta && typeof chatMeta === 'object' && Object.keys(chatMeta).length > 0) {
		return chatMeta;
	}

	const activeProfile = normalizeSessionValue(runtime?.active_profile);
	const activeHome = normalizeSessionValue(runtime?.active_home);
	const activeTargetId = normalizeSessionValue(runtime?.target_id);

	if (!activeProfile && !activeHome) {
		return null;
	}

	return {
		...(activeTargetId ? { target_id: activeTargetId, runtime_target_id: activeTargetId } : {}),
		...(activeProfile ? { profile: activeProfile } : {}),
		...(activeHome ? { active_home: activeHome } : {})
	};
};

export const countHermesSessionsByScope = (
	sessions: HermesSessionListItem[],
	{ currentChatId = null, currentSessionId = null }: HermesCurrentSessionOptions = {}
) => ({
	all: sessions.length,
	imported: sessions.filter((session) => Boolean(session.imported_chat_id)).length,
	current: sessions.filter((session) =>
		isCurrentHermesSession(session, { currentChatId, currentSessionId })
	).length
});

export const getHiddenAuxiliaryHermesSessions = (
	sessions: HermesSessionListItem[],
	{ currentChatId = null, currentSessionId = null }: HermesCurrentSessionOptions = {}
) =>
	sessions.filter(
		(session) =>
			session.is_auxiliary_cli_session &&
			!session.imported_chat_id &&
			!isCurrentHermesSession(session, { currentChatId, currentSessionId })
	);

export const getRecentVisibleHermesSessions = (
	sessions: HermesSessionListItem[],
	{
		limit = 5,
		currentChatId = null,
		currentSessionId = null,
		includeImported = false,
		includeAuxiliary = false
	}: {
		limit?: number;
		currentChatId?: string | null;
		currentSessionId?: string | null;
		includeImported?: boolean;
		includeAuxiliary?: boolean;
	} = {}
) =>
	sessions
		.filter((session) => {
			const isCurrent = isCurrentHermesSession(session, { currentChatId, currentSessionId });

			if (!includeImported && session.imported_chat_id) {
				return false;
			}

			if (!includeAuxiliary && session.is_auxiliary_cli_session && !isCurrent) {
				return false;
			}

			return true;
		})
		.sort((left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0))
		.slice(0, Math.max(0, limit));

export const filterHermesSessions = (
	sessions: HermesSessionListItem[],
	{
		query = '',
		scope = 'all',
		currentChatId = null,
		currentSessionId = null
	}: {
		query?: string;
		scope?: HermesSessionScope;
		currentChatId?: string | null;
		currentSessionId?: string | null;
	} = {}
) => {
	const normalizedQuery = normalizeSearchValue(query);

	return sessions.filter((session) => {
		if (scope === 'imported' && !session.imported_chat_id) {
			return false;
		}

		if (
			scope === 'current' &&
			!isCurrentHermesSession(session, { currentChatId, currentSessionId })
		) {
			return false;
		}

		if (!normalizedQuery) {
			return true;
		}

		return getSearchHaystack(session).includes(normalizedQuery);
	});
};

export const getSearchableHermesSessions = (
	sessions: HermesSessionListItem[],
	{
		query = '',
		scope = 'all',
		currentChatId = null,
		currentSessionId = null,
		includeAuxiliary = true
	}: {
		query?: string;
		scope?: HermesSessionScope;
		currentChatId?: string | null;
		currentSessionId?: string | null;
		includeAuxiliary?: boolean;
	} = {}
) => {
	const hiddenAuxiliarySessions = includeAuxiliary
		? []
		: getHiddenAuxiliaryHermesSessions(sessions, {
				currentChatId,
				currentSessionId
			});

	return filterHermesSessions(
		hiddenAuxiliarySessions.length > 0
			? sessions.filter((session) => !hiddenAuxiliarySessions.includes(session))
			: sessions,
		{
			query,
			scope,
			currentChatId,
			currentSessionId
		}
	).sort((left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0));
};

export const groupHermesSessionsByTimeRange = (sessions: HermesSessionListItem[]) => {
	const groups: HermesSessionGroup[] = [];

	for (const session of sessions) {
		const label = session.time_range || 'Earlier';
		const currentGroup = groups[groups.length - 1];

		if (!currentGroup || currentGroup.label !== label) {
			groups.push({ label, items: [session] });
			continue;
		}

		currentGroup.items.push(session);
	}

	return groups;
};

export const getHermesChatMeta = (
	meta: Record<string, any> | null | undefined
): HermesChatMeta | null => (meta?.hermes && typeof meta.hermes === 'object' ? meta.hermes : null);

export const resolveHermesChatMeta = (
	meta: Record<string, any> | null | undefined,
	chatPayload: Record<string, any> | null | undefined = null
): HermesChatMeta | null =>
	getHermesChatMeta(meta) ??
	(chatPayload?.hermesSession && typeof chatPayload.hermesSession === 'object'
		? chatPayload.hermesSession
		: null);

export const getResolvedHermesSessionContext = ({
	session = null,
	meta = null,
	chatPayload = null,
	runtime = null
}: {
	session?: Record<string, any> | null;
	meta?: Record<string, any> | null;
	chatPayload?: Record<string, any> | null;
	runtime?: HermesRuntimeContext | null;
} = {}) => {
	const persistedSession = session && typeof session === 'object' ? session : null;
	const resolvedMeta = resolveHermesChatMeta(meta, chatPayload);

	const sessionId =
		normalizeSessionValue(persistedSession?.session_id) ??
		normalizeSessionValue(resolvedMeta?.session_id);
	const model =
		normalizeSessionValue(persistedSession?.model) ?? normalizeSessionValue(resolvedMeta?.model);
	const profile =
		normalizeSessionValue(persistedSession?.profile) ??
		normalizeSessionValue(resolvedMeta?.profile) ??
		normalizeSessionValue(runtime?.active_profile);
	const activeHome =
		normalizeSessionValue(persistedSession?.active_home) ??
		normalizeSessionValue(resolvedMeta?.active_home) ??
		normalizeSessionValue(runtime?.active_home);
	const sourceTag =
		normalizeSessionValue(persistedSession?.source_tag ?? persistedSession?.source) ??
		normalizeSessionValue(resolvedMeta?.source_tag ?? resolvedMeta?.source);
	const targetId =
		normalizeSessionValue(persistedSession?.runtime_target_id ?? persistedSession?.target_id) ??
		normalizeSessionValue(resolvedMeta?.runtime_target_id ?? resolvedMeta?.target_id) ??
		normalizeSessionValue(runtime?.target_id);
	const baseContext =
		(persistedSession ?? resolvedMeta) && typeof (persistedSession ?? resolvedMeta) === 'object'
			? { ...(persistedSession ?? resolvedMeta) }
			: null;

	if (!sessionId && !model && !profile && !activeHome && !sourceTag && !targetId) {
		return null;
	}

	return {
		...(baseContext ?? {}),
		...(sessionId ? { session_id: sessionId } : {}),
		...(model ? { model } : {}),
		...(profile ? { profile } : {}),
		...(activeHome ? { active_home: activeHome } : {}),
		...(sourceTag ? { source_tag: sourceTag } : {}),
		...(targetId ? { target_id: targetId, runtime_target_id: targetId } : {})
	};
};

export const formatHermesSourceLabel = (sourceTag: string | null | undefined) => {
	const normalizedSourceTag = normalizeSessionValue(sourceTag);

	if (!normalizedSourceTag) {
		return '';
	}

	return HERMES_SOURCE_LABELS[normalizedSourceTag.toLowerCase()] ?? normalizedSourceTag;
};

export const formatHermesSourceLabels = (sourceTags: (string | null | undefined)[] = []) =>
	Array.from(
		new Set(
			sourceTags
				.map((sourceTag) => normalizeSessionValue(sourceTag)?.toLowerCase() ?? null)
				.filter(Boolean)
		)
	)
		.sort(
			(sourceA, sourceB) =>
				(HERMES_SOURCE_LABEL_ORDER[sourceA] ?? Number.MAX_SAFE_INTEGER) -
					(HERMES_SOURCE_LABEL_ORDER[sourceB] ?? Number.MAX_SAFE_INTEGER) ||
				sourceA.localeCompare(sourceB)
		)
		.map((sourceTag) => formatHermesSourceLabel(sourceTag));

export const getHermesSessionSourceLabels = (session: HermesSessionListItem) => {
	const normalizedSourceTags = [
		normalizeSessionValue(session.source_tag)?.toLowerCase() ?? null,
		...(session.available_sources ?? []).map(
			(sourceTag) => normalizeSessionValue(sourceTag)?.toLowerCase() ?? null
		)
	].filter(Boolean) as string[];

	const uniqueSourceTags = Array.from(new Set(normalizedSourceTags));

	return uniqueSourceTags
		.sort((left, right) => {
			const leftIndex = HERMES_SOURCE_ORDER.indexOf(left);
			const rightIndex = HERMES_SOURCE_ORDER.indexOf(right);

			if (leftIndex === -1 && rightIndex === -1) {
				return left.localeCompare(right);
			}

			if (leftIndex === -1) {
				return 1;
			}

			if (rightIndex === -1) {
				return -1;
			}

			return leftIndex - rightIndex;
		})
		.map((sourceTag) => formatHermesSourceLabel(sourceTag));
};

export const buildHermesSessionMapByImportedChatId = <T extends HermesSessionListItem>(
	sessions: T[] = []
): Record<string, T> => {
	const sessionMap: Record<string, T> = {};

	for (const session of sessions) {
		const importedChatId = normalizeSessionValue(session.imported_chat_id);

		if (!importedChatId || sessionMap[importedChatId]) {
			continue;
		}

		sessionMap[importedChatId] = session;
	}

	return sessionMap;
};

export const setHermesSessionStores = <T extends HermesSessionListItem>(sessions: T[] = []) => {
	hermesRecentSessions.set(sessions);
	hermesSessionsByChatId.set(buildHermesSessionMapByImportedChatId(sessions));
	return sessions;
};

export const refreshHermesSessionStores = async (token: string) => {
	const sessionsPayload = await getHermesSessions(token);
	return setHermesSessionStores((sessionsPayload?.items ?? []) as HermesSessionListItem[]);
};

export const getHermesEffectiveUpdatedAt = (
	chat: Pick<HermesAwareChatListItem, 'id' | 'updated_at'> | null | undefined,
	sessionsByChatId: HermesSessionMapByImportedChatId = {}
) => {
	if (!chat?.id) {
		return chat?.updated_at ?? null;
	}

	const chatUpdatedAt = chat.updated_at ?? null;
	const sessionUpdatedAt = sessionsByChatId[chat.id]?.updated_at ?? null;

	if (chatUpdatedAt === null) {
		return sessionUpdatedAt;
	}

	if (sessionUpdatedAt === null) {
		return chatUpdatedAt;
	}

	return Math.max(chatUpdatedAt, sessionUpdatedAt);
};

export const buildHermesAwareChatList = (
	chats: HermesAwareChatListItem[] = [],
	sessionsByChatId: HermesSessionMapByImportedChatId = {},
	{
		orderBy = 'updated_at',
		direction = 'desc'
	}: {
		orderBy?: string;
		direction?: 'asc' | 'desc';
	} = {}
) =>
	chats
		.map((chat, index) => {
			const effectiveUpdatedAt = getHermesEffectiveUpdatedAt(chat, sessionsByChatId);

			return {
				...chat,
				effective_updated_at: effectiveUpdatedAt,
				time_range:
					orderBy === 'updated_at' && effectiveUpdatedAt
						? getTimeRange(effectiveUpdatedAt)
						: (chat.time_range ?? (chat.updated_at ? getTimeRange(chat.updated_at) : null)),
				__hermes_order_index: index
			};
		})
		.sort((left, right) => {
			const leftValue =
				orderBy === 'updated_at'
					? (left.effective_updated_at ?? left.updated_at ?? 0)
					: left[orderBy];
			const rightValue =
				orderBy === 'updated_at'
					? (right.effective_updated_at ?? right.updated_at ?? 0)
					: right[orderBy];

			if (leftValue === rightValue) {
				return left.__hermes_order_index - right.__hermes_order_index;
			}

			if (direction === 'asc') {
				return leftValue > rightValue ? 1 : -1;
			}

			return leftValue < rightValue ? 1 : -1;
		})
		.map(({ __hermes_order_index, ...chat }) => chat);

export const buildHermesImportedSessionsRefreshSignature = (
	sessions: HermesSessionListItem[] = [],
	{ importedSessionLimit = 20 }: Pick<HermesLoadedChatsRefreshOptions, 'importedSessionLimit'> = {}
) =>
	sessions
		.filter((session) => Boolean(session.imported_chat_id) && !session.imported_chat_archived)
		.sort((left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0))
		.slice(0, Math.max(0, importedSessionLimit))
		.map((session) => `${session.imported_chat_id ?? ''}:${session.updated_at ?? 0}`)
		.join('|');

export const shouldRefreshLoadedChatsForHermesSessions = (
	sessions: HermesSessionListItem[] = [],
	chats: HermesAwareChatListItem[] = [],
	pinnedChats: HermesAwareChatListItem[] = [],
	{ pageSize = 60, importedSessionLimit = 20 }: HermesLoadedChatsRefreshOptions = {}
) => {
	const loadedChatsById = new Map(
		[...pinnedChats, ...chats]
			.filter((chat) => Boolean(chat?.id))
			.map((chat) => [chat.id, chat] as const)
	);
	const primaryChatPage = chats.slice(0, Math.max(0, pageSize));
	const pageBoundaryUpdatedAt =
		primaryChatPage.length > 0
			? Math.min(...primaryChatPage.map((chat) => chat.updated_at ?? 0))
			: null;

	for (const session of sessions
		.filter((item) => Boolean(item.imported_chat_id) && !item.imported_chat_archived)
		.sort((left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0))
		.slice(0, Math.max(0, importedSessionLimit))) {
		const importedChatId = normalizeSessionValue(session.imported_chat_id);
		const sessionUpdatedAt = session.updated_at ?? 0;

		if (!importedChatId || sessionUpdatedAt <= 0) {
			continue;
		}

		const loadedChat = loadedChatsById.get(importedChatId);
		if (loadedChat) {
			if (sessionUpdatedAt > (loadedChat.updated_at ?? 0)) {
				return true;
			}

			continue;
		}

		if (pageBoundaryUpdatedAt === null || sessionUpdatedAt > pageBoundaryUpdatedAt) {
			return true;
		}
	}

	return false;
};

export const formatHermesSessionSourceLine = (session: HermesSessionListItem) =>
	getHermesSessionSourceLabels(session).join(' · ');

export const formatHermesContextLabel = (
	hermesMeta: HermesChatMeta | null,
	{ includeCliSource = false }: { includeCliSource?: boolean } = {}
) => {
	if (!hermesMeta) {
		return '';
	}

	return [
		'Hermes',
		hermesMeta.profile && hermesMeta.profile !== 'default' ? hermesMeta.profile : null,
		hermesMeta.source_tag && (includeCliSource || hermesMeta.source_tag !== 'cli')
			? formatHermesSourceLabel(hermesMeta.source_tag)
			: null
	]
		.filter(Boolean)
		.join(' • ');
};

export const getHermesContextBadges = (
	hermesMeta: HermesChatMeta | null,
	{
		includeBaseLabel = true,
		includeDefaultProfile = false,
		includeCliSource = false
	}: HermesContextBadgeOptions = {}
) => {
	if (!hermesMeta) {
		return [];
	}

	return [
		includeBaseLabel ? 'Hermes' : null,
		hermesMeta.profile && (includeDefaultProfile || hermesMeta.profile !== 'default')
			? hermesMeta.profile
			: null,
		hermesMeta.source_tag && (includeCliSource || hermesMeta.source_tag !== 'cli')
			? formatHermesSourceLabel(hermesMeta.source_tag)
			: null
	].filter(Boolean);
};

export const getHermesChatSidebarBadges = ({
	hermesMeta = null,
	session = null,
	includeDefaultProfile = false,
	includeCliSource = true,
	includeAuxiliary = true
}: {
	hermesMeta?: HermesChatMeta | null;
	session?: HermesSessionListItem | null;
	includeDefaultProfile?: boolean;
	includeCliSource?: boolean;
	includeAuxiliary?: boolean;
} = {}) => {
	const profile = session?.profile ?? hermesMeta?.profile ?? null;
	const sourceLabels = session
		? getHermesSessionSourceLabels(session)
		: formatHermesSourceLabels([hermesMeta?.source_tag]);
	const primarySourceLabel = sourceLabels.length <= 1 ? sourceLabels[0] : null;

	if (!profile && sourceLabels.length === 0 && !session && !hermesMeta) {
		return [];
	}

	return [
		'Hermes',
		profile && (includeDefaultProfile || profile !== 'default') ? profile : null,
		primarySourceLabel && (includeCliSource || primarySourceLabel !== 'CLI')
			? primarySourceLabel
			: null,
		includeAuxiliary && session?.is_auxiliary_cli_session ? 'Auxiliary' : null
	].filter(Boolean);
};

export const buildHermesSessionSummaryFromMessages = (messages: any[] = []) => {
	const assistantMessages = messages.filter((message) => message?.role === 'assistant');

	if (assistantMessages.length === 0) {
		return null;
	}

	const operationalTurnCount = assistantMessages.filter(
		(message) =>
			!!message?.hermesApproval ||
			(message?.statusHistory?.length ?? 0) > 0 ||
			(message?.code_executions?.length ?? 0) > 0
	).length;

	return {
		latest_assistant_model: assistantMessages
			.map((message) => message?.model)
			.filter(Boolean)
			.at(-1),
		assistant_reply_count: assistantMessages.length,
		operational_turn_count: operationalTurnCount
	};
};

const formatModelLabel = (modelId: string | null | undefined) => {
	if (!modelId) {
		return '';
	}

	return modelId.split('/').pop() ?? modelId;
};

export const formatHermesSessionMetaLine = (
	summary: Record<string, any> | null,
	translate: (key: string, options?: Record<string, number>) => string
) => {
	if (!summary || typeof summary !== 'object') {
		return '';
	}

	const assistantReplyCount = summary.assistant_reply_count ?? 0;
	const operationalTurnCount = summary.operational_turn_count ?? 0;

	return [
		formatModelLabel(summary.latest_assistant_model),
		operationalTurnCount > 0
			? operationalTurnCount === 1
				? translate('1 op')
				: translate('{{COUNT}} ops', { COUNT: operationalTurnCount })
			: null,
		assistantReplyCount > 0
			? assistantReplyCount === 1
				? translate('1 reply')
				: translate('{{COUNT}} replies', { COUNT: assistantReplyCount })
			: null
	]
		.filter(Boolean)
		.join(' • ');
};

const formatHermesSessionActivityLine = (
	summary: Record<string, any> | null,
	translate: (key: string, options?: Record<string, number>) => string
) => {
	if (!summary || typeof summary !== 'object') {
		return '';
	}

	const assistantReplyCount = summary.assistant_reply_count ?? 0;
	const operationalTurnCount = summary.operational_turn_count ?? 0;

	return [
		operationalTurnCount > 0
			? operationalTurnCount === 1
				? translate('1 op')
				: translate('{{COUNT}} ops', { COUNT: operationalTurnCount })
			: null,
		assistantReplyCount > 0
			? assistantReplyCount === 1
				? translate('1 reply')
				: translate('{{COUNT}} replies', { COUNT: assistantReplyCount })
			: null
	]
		.filter(Boolean)
		.join(' • ');
};

export const formatHermesChatSidebarMetaLine = ({
	summary,
	session,
	translate
}: {
	summary: Record<string, any> | null;
	session?: HermesSessionListItem | null;
	translate: (key: string, options?: Record<string, number>) => string;
}) => {
	const summaryLine = formatHermesSessionActivityLine(summary, translate);
	const sourceLabels = session ? getHermesSessionSourceLabels(session) : [];
	const sourceLine = sourceLabels.length > 1 ? sourceLabels.join(' · ') : '';

	return [summaryLine, sourceLine].filter(Boolean).join(' • ');
};

export const formatHermesChatListMetaLine = ({
	hermesMeta,
	session = null,
	summary,
	translate,
	includeCliSource = true
}: {
	hermesMeta: HermesChatMeta | null;
	session?: HermesSessionListItem | null;
	summary: Record<string, any> | null;
	translate: (key: string, options?: Record<string, number>) => string;
	includeCliSource?: boolean;
}) =>
	[
		getHermesChatSidebarBadges({
			hermesMeta,
			session,
			includeCliSource,
			includeAuxiliary: true
		}).join(' • '),
		formatHermesSessionActivityLine(summary, translate),
		session && getHermesSessionSourceLabels(session).length > 1
			? formatHermesSessionSourceLine(session)
			: null
	]
		.filter(Boolean)
		.join(' • ');

export const getHermesSessionActivityLabel = (
	updatedAt: number | null | undefined
): HermesSessionActivityLabel => {
	if (!updatedAt) {
		return {
			key: 'Recently'
		};
	}

	const timestamp = updatedAt * 1000;

	return {
		key: formatDate(timestamp),
		values: {
			LOCALIZED_TIME: dayjs(timestamp).format('LT'),
			LOCALIZED_DATE: dayjs(timestamp).format('L')
		}
	};
};
