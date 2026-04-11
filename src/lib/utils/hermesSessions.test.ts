import dayjs from 'dayjs';
import { afterEach, describe, expect, test, vi } from 'vitest';

import {
	buildHermesAwareChatList,
	buildHermesImportedSessionsRefreshSignature,
	buildHermesSessionMapByImportedChatId,
	buildHermesSessionSummaryFromMessages,
	countHermesSessionsByScope,
	filterHermesSessions,
	formatHermesChatSidebarMetaLine,
	formatHermesChatListMetaLine,
	formatHermesScopedCount,
	getHermesChatSidebarBadges,
	formatHermesContextLabel,
	formatHermesSessionSourceLine,
	formatHermesSourceLabel,
	formatHermesSourceLabels,
	formatHermesSessionMetaLine,
	getRecentVisibleHermesSessions,
	getHermesChatMeta,
	getHermesContextBadges,
	getHermesEffectiveUpdatedAt,
	getHermesModelSourceLabelKey,
	getHiddenAuxiliaryHermesSessions,
	getPersistedHermesSessionContext,
	getResolvedHermesSessionContext,
	getSearchableHermesSessions,
	getHermesSessionSourceLabels,
	getHermesSessionStateLabelKey,
	getHermesSessionActivityLabel,
	groupHermesSessionsByTimeRange,
	isCurrentHermesSession,
	resolveHermesChatMeta,
	shouldRefreshLoadedChatsForHermesSessions,
	type HermesSessionListItem
} from './hermesSessions';

const SESSIONS: HermesSessionListItem[] = [
	{
		session_id: 'session-current',
		title: 'Assess Hermes CLI continuity',
		model: 'openai/gpt-5.4',
		profile: 'default',
		source_tag: 'cli',
		last_user_content: 'Continue the current Hermes session',
		imported_chat_id: 'chat-1',
		time_range: 'Today'
	},
	{
		session_id: 'session-imported',
		title: 'Imported archive candidate',
		model: 'gpt-4o-mini',
		profile: 'work',
		source_tag: 'json',
		last_user_content: 'Older imported transcript',
		imported_chat_id: 'chat-2',
		time_range: 'Yesterday'
	},
	{
		session_id: 'session-fresh',
		title: 'Inspect worker noise',
		model: 'gpt-5.4',
		profile: 'ops',
		source_tag: 'state_db',
		last_user_content: 'Inspect helper behavior',
		time_range: 'Yesterday'
	}
];

describe('countHermesSessionsByScope', () => {
	test('counts all, imported, and current sessions', () => {
		expect(countHermesSessionsByScope(SESSIONS, { currentChatId: 'chat-1' })).toEqual({
			all: 3,
			imported: 2,
			current: 1
		});
	});

	test('counts current sessions by Hermes session id when no imported chat mapping exists', () => {
		expect(countHermesSessionsByScope(SESSIONS, { currentSessionId: 'session-fresh' })).toEqual({
			all: 3,
			imported: 2,
			current: 1
		});
	});
});

describe('filterHermesSessions', () => {
	test('filters imported and current scopes without changing order', () => {
		expect(filterHermesSessions(SESSIONS, { scope: 'imported', currentChatId: 'chat-1' })).toEqual([
			SESSIONS[0],
			SESSIONS[1]
		]);

		expect(filterHermesSessions(SESSIONS, { scope: 'current', currentChatId: 'chat-1' })).toEqual([
			SESSIONS[0]
		]);
	});

	test('filters the current scope by Hermes session id for live non-imported chats', () => {
		expect(
			filterHermesSessions(SESSIONS, { scope: 'current', currentSessionId: 'session-fresh' })
		).toEqual([SESSIONS[2]]);
	});

	test('matches search against title, content, model label, source, and session id', () => {
		expect(filterHermesSessions(SESSIONS, { query: 'worker noise' })).toEqual([SESSIONS[2]]);
		expect(filterHermesSessions(SESSIONS, { query: 'current Hermes session' })).toEqual([
			SESSIONS[0]
		]);
		expect(filterHermesSessions(SESSIONS, { query: 'gpt-4o-mini' })).toEqual([SESSIONS[1]]);
		expect(filterHermesSessions(SESSIONS, { query: 'state_db' })).toEqual([SESSIONS[2]]);
		expect(filterHermesSessions(SESSIONS, { query: 'session-current' })).toEqual([SESSIONS[0]]);
		expect(filterHermesSessions(SESSIONS, { query: 'ops' })).toEqual([SESSIONS[2]]);
	});

	test('matches search against merged available sources, not only the primary source tag', () => {
		const mergedSession = {
			...SESSIONS[0],
			source_tag: 'cli',
			available_sources: ['json', 'state_db', 'webui']
		};

		expect(filterHermesSessions([mergedSession], { query: 'webui' })).toEqual([mergedSession]);
	});
});

describe('isCurrentHermesSession', () => {
	test('matches current sessions by imported chat id or Hermes session id', () => {
		expect(isCurrentHermesSession(SESSIONS[0], { currentChatId: 'chat-1' })).toBe(true);
		expect(isCurrentHermesSession(SESSIONS[2], { currentSessionId: 'session-fresh' })).toBe(true);
		expect(
			isCurrentHermesSession(SESSIONS[1], {
				currentChatId: 'chat-1',
				currentSessionId: 'session-fresh'
			})
		).toBe(false);
	});
});

describe('getHiddenAuxiliaryHermesSessions', () => {
	test('keeps the current auxiliary Hermes session visible while hiding the rest', () => {
		const auxiliarySessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				session_id: 'session-current-helper',
				imported_chat_id: null,
				is_auxiliary_cli_session: true
			},
			{
				...SESSIONS[1],
				session_id: 'session-hidden-helper',
				imported_chat_id: null,
				is_auxiliary_cli_session: true
			},
			SESSIONS[2]
		];

		expect(
			getHiddenAuxiliaryHermesSessions(auxiliarySessions, {
				currentSessionId: 'session-current-helper'
			})
		).toEqual([auxiliarySessions[1]]);
	});

	test('keeps imported auxiliary sessions visible by default', () => {
		const importedAuxiliarySession = {
			...SESSIONS[1],
			session_id: 'session-imported-helper',
			imported_chat_id: 'chat-imported-helper',
			is_auxiliary_cli_session: true
		};

		expect(getHiddenAuxiliaryHermesSessions([importedAuxiliarySession], {})).toEqual([]);
	});
});

describe('getRecentVisibleHermesSessions', () => {
	test('returns recent non-imported sessions and hides auxiliary sessions by default', () => {
		const sessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				session_id: 'session-old',
				updated_at: 100
			},
			{
				...SESSIONS[1],
				session_id: 'session-aux',
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 400
			},
			{
				...SESSIONS[2],
				session_id: 'session-new',
				imported_chat_id: null,
				updated_at: 800
			}
		];

		expect(getRecentVisibleHermesSessions(sessions, { limit: 5 })).toEqual([sessions[2]]);
	});

	test('keeps the current auxiliary session visible and respects the requested limit', () => {
		const sessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				session_id: 'session-current-aux',
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 600
			},
			{
				...SESSIONS[1],
				session_id: 'session-hidden-aux',
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 500
			},
			{
				...SESSIONS[2],
				session_id: 'session-visible',
				imported_chat_id: null,
				updated_at: 400
			}
		];

		expect(
			getRecentVisibleHermesSessions(sessions, {
				currentSessionId: 'session-current-aux',
				limit: 2
			})
		).toEqual([sessions[0], sessions[2]]);
	});
});

describe('getSearchableHermesSessions', () => {
	test('returns filtered sessions in freshest-first order for modal discovery', () => {
		const sessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				session_id: 'session-older',
				updated_at: 100
			},
			{
				...SESSIONS[1],
				session_id: 'session-newest',
				updated_at: 800,
				last_user_content: 'Investigate the latest sync issue'
			},
			{
				...SESSIONS[2],
				session_id: 'session-middle',
				updated_at: 400,
				last_user_content: 'Inspect worker noise'
			}
		];

		expect(getSearchableHermesSessions(sessions, { query: 'issue' })).toEqual([sessions[1]]);
		expect(getSearchableHermesSessions(sessions)).toEqual([sessions[1], sessions[2], sessions[0]]);
	});

	test('can hide non-current auxiliary sessions while keeping imported/current ones discoverable', () => {
		const sessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				session_id: 'session-current-helper',
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 600
			},
			{
				...SESSIONS[1],
				session_id: 'session-imported-helper',
				imported_chat_id: 'chat-imported-helper',
				is_auxiliary_cli_session: true,
				updated_at: 500
			},
			{
				...SESSIONS[2],
				session_id: 'session-hidden-helper',
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 400
			}
		];

		expect(
			getSearchableHermesSessions(sessions, {
				includeAuxiliary: false,
				currentSessionId: 'session-current-helper'
			})
		).toEqual([sessions[0], sessions[1]]);
	});
});

describe('buildHermesSessionMapByImportedChatId', () => {
	test('indexes imported sessions by chat id without overwriting the newest item order', () => {
		expect(
			buildHermesSessionMapByImportedChatId([
				SESSIONS[0],
				SESSIONS[1],
				{ ...SESSIONS[2], imported_chat_id: 'chat-2' }
			])
		).toEqual({
			'chat-1': SESSIONS[0],
			'chat-2': SESSIONS[1]
		});
	});
});

describe('Hermes-aware chat freshness', () => {
	test('prefers fresher linked Hermes session timestamps for list ordering and time buckets', () => {
		const sessionsByChatId = buildHermesSessionMapByImportedChatId([
			{ ...SESSIONS[1], imported_chat_id: 'chat-stale', updated_at: 2_000_000_000 }
		]);
		const orderedChats = buildHermesAwareChatList(
			[
				{
					id: 'chat-plain',
					title: 'Plain chat',
					updated_at: 1_900_000_000,
					created_at: 1_899_999_000,
					time_range: 'Yesterday'
				},
				{
					id: 'chat-stale',
					title: 'Imported stale chat',
					updated_at: 1_700_000_000,
					created_at: 1_699_999_000,
					time_range: 'Previous 30 days'
				}
			],
			sessionsByChatId
		);

		expect(getHermesEffectiveUpdatedAt(orderedChats[0], sessionsByChatId)).toBe(2_000_000_000);
		expect(orderedChats.map((chat) => chat.id)).toEqual(['chat-stale', 'chat-plain']);
		expect(orderedChats[0].effective_updated_at).toBe(2_000_000_000);
		expect(orderedChats[0].time_range).toBeTypeOf('string');
	});

	test('keeps legacy ordering for chats without a fresher linked Hermes session', () => {
		const sessionsByChatId = buildHermesSessionMapByImportedChatId([
			{ ...SESSIONS[0], imported_chat_id: 'chat-linked', updated_at: 1_500 }
		]);
		const orderedChats = buildHermesAwareChatList(
			[
				{
					id: 'chat-first',
					title: 'First chat',
					updated_at: 3_000,
					created_at: 2_900,
					time_range: 'Today'
				},
				{
					id: 'chat-linked',
					title: 'Linked chat',
					updated_at: 2_000,
					created_at: 1_900,
					time_range: 'Today'
				},
				{
					id: 'chat-missing',
					title: 'Missing session chat',
					updated_at: 1_000,
					created_at: 900,
					time_range: 'Yesterday'
				}
			],
			sessionsByChatId
		);

		expect(orderedChats.map((chat) => chat.id)).toEqual([
			'chat-first',
			'chat-linked',
			'chat-missing'
		]);
		expect(orderedChats[1].effective_updated_at).toBe(2_000);
		expect(orderedChats[2].effective_updated_at).toBe(1_000);
	});

	test('requests a sidebar chat-list refresh when fresher imported Hermes sessions outpace loaded chats', () => {
		const sessions: HermesSessionListItem[] = [
			{ ...SESSIONS[0], imported_chat_id: 'chat-loaded', updated_at: 4_000 },
			{ ...SESSIONS[1], imported_chat_id: 'chat-missing', updated_at: 3_500 }
		];
		const chats = [
			{
				id: 'chat-loaded',
				title: 'Loaded imported chat',
				updated_at: 2_000
			},
			{
				id: 'chat-boundary',
				title: 'Boundary chat',
				updated_at: 3_000
			}
		];

		expect(
			shouldRefreshLoadedChatsForHermesSessions(sessions, chats, [], {
				pageSize: 2,
				importedSessionLimit: 10
			})
		).toBe(true);
		expect(
			buildHermesImportedSessionsRefreshSignature(sessions, {
				importedSessionLimit: 10
			})
		).toBe('chat-loaded:4000|chat-missing:3500');
	});

	test('builds imported refresh signatures from the freshest imported sessions regardless of input order', () => {
		const sessions: HermesSessionListItem[] = [
			{ ...SESSIONS[0], imported_chat_id: 'chat-old', updated_at: 1_000 },
			{ ...SESSIONS[1], imported_chat_id: 'chat-new', updated_at: 5_000 },
			{ ...SESSIONS[2], imported_chat_id: 'chat-mid', updated_at: 3_000 }
		];

		expect(
			buildHermesImportedSessionsRefreshSignature(sessions, {
				importedSessionLimit: 2
			})
		).toBe('chat-new:5000|chat-mid:3000');
	});

	test('skips sidebar chat-list refresh when imported freshness is unchanged and only auxiliary or metadata shifts', () => {
		const sessions: HermesSessionListItem[] = [
			{
				...SESSIONS[0],
				imported_chat_id: 'chat-loaded',
				updated_at: 2_000,
				title: 'Same freshness, new title'
			},
			{
				...SESSIONS[1],
				imported_chat_id: null,
				is_auxiliary_cli_session: true,
				updated_at: 9_000
			}
		];
		const chats = [
			{
				id: 'chat-loaded',
				title: 'Loaded imported chat',
				updated_at: 2_000
			},
			{
				id: 'chat-boundary',
				title: 'Boundary chat',
				updated_at: 1_500
			}
		];

		expect(
			shouldRefreshLoadedChatsForHermesSessions(sessions, chats, [], {
				pageSize: 2,
				importedSessionLimit: 10
			})
		).toBe(false);
	});
});

describe('getHermesSessionStateLabelKey', () => {
	test('prefers temporary and active Hermes session states over generic current chat state', () => {
		expect(getHermesSessionStateLabelKey({ temporaryChatEnabled: true })).toBe('Temporary Chat');
		expect(
			getHermesSessionStateLabelKey({
				currentHermesSessionId: 'session-current',
				currentMessageId: 'assistant-1'
			})
		).toBe('Active');
		expect(getHermesSessionStateLabelKey({ currentMessageId: 'assistant-1' })).toBe('Current chat');
		expect(getHermesSessionStateLabelKey()).toBe('');
	});
});

describe('getPersistedHermesSessionContext', () => {
	test('prefers existing chat Hermes context over runtime-derived fallback', () => {
		expect(
			getPersistedHermesSessionContext({
				chatHermesSession: {
					session_id: 'imported123',
					profile: 'work',
					source_tag: 'cli'
				},
				runtime: {
					active_profile: 'default',
					active_home: '/Users/martin/.hermes'
				}
			})
		).toEqual({
			session_id: 'imported123',
			profile: 'work',
			source_tag: 'cli'
		});
	});

	test('falls back to chat meta and then runtime profile/home without inventing a session id', () => {
		expect(
			getPersistedHermesSessionContext({
				chatMeta: {
					profile: 'ops'
				},
				runtime: {
					active_profile: 'default',
					active_home: '/Users/martin/.hermes'
				}
			})
		).toEqual({
			profile: 'ops'
		});

		expect(
			getPersistedHermesSessionContext({
				runtime: {
					active_profile: 'work',
					active_home: '/Users/martin/.hermes/profiles/work'
				}
			})
		).toEqual({
			profile: 'work',
			active_home: '/Users/martin/.hermes/profiles/work'
		});

		expect(getPersistedHermesSessionContext()).toBeNull();
	});

	test('ignores empty persisted chat Hermes objects and falls back to runtime context', () => {
		expect(
			getPersistedHermesSessionContext({
				chatHermesSession: {},
				runtime: {
					active_profile: 'default',
					active_home: '/Users/martin/.hermes'
				}
			})
		).toEqual({
			profile: 'default',
			active_home: '/Users/martin/.hermes'
		});
	});
});

describe('getResolvedHermesSessionContext', () => {
	test('merges session, meta, and runtime fields without dropping richer persisted identity', () => {
		expect(
			getResolvedHermesSessionContext({
				session: {
					session_id: 'session-imported',
					profile: 'work'
				},
				meta: {
					hermes: {
						session_id: '   ',
						model: 'openai/gpt-5.4',
						profile: 'ops',
						source_tag: 'cli'
					}
				},
				runtime: {
					active_profile: 'default',
					active_home: '/Users/martin/.hermes/profiles/default',
					target_id: 'remote'
				}
			})
		).toEqual({
			session_id: 'session-imported',
			profile: 'work',
			model: 'openai/gpt-5.4',
			source_tag: 'cli',
			active_home: '/Users/martin/.hermes/profiles/default',
			target_id: 'remote',
			runtime_target_id: 'remote'
		});
	});

	test('normalizes the same Hermes context from either meta or payload session input', () => {
		const expected = {
			session_id: 'session-live',
			model: 'openai/gpt-5.4',
			profile: 'default',
			source_tag: 'state_db',
			target_id: 'local',
			runtime_target_id: 'local'
		};

		expect(
			getResolvedHermesSessionContext({
				meta: {
					hermes: {
						...expected
					}
				}
			})
		).toEqual(expected);

		expect(
			getResolvedHermesSessionContext({
				chatPayload: {
					hermesSession: {
						...expected
					}
				}
			})
		).toEqual(expected);
	});
});

describe('getHermesChatSidebarBadges', () => {
	test('keeps sidebar badges compact while still surfacing auxiliary imported sessions', () => {
		expect(
			getHermesChatSidebarBadges({
				hermesMeta: {
					session_id: 'session-imported',
					profile: 'default',
					source_tag: 'cli'
				},
				session: {
					...SESSIONS[1],
					source_tag: 'cli',
					available_sources: ['cli', 'json', 'state_db'],
					is_auxiliary_cli_session: true
				}
			})
		).toEqual(['Hermes', 'work', 'Auxiliary']);
	});

	test('falls back to the primary source badge when only a single source exists', () => {
		expect(
			getHermesChatSidebarBadges({
				hermesMeta: {
					session_id: 'session-current',
					profile: 'default',
					source_tag: 'cli'
				},
				session: SESSIONS[0]
			})
		).toEqual(['Hermes', 'CLI']);
	});
});

describe('formatHermesChatSidebarMetaLine', () => {
	test('appends multi-source provenance after the summary line for sidebar rows', () => {
		expect(
			formatHermesChatSidebarMetaLine({
				summary: {
					latest_assistant_model: 'openai/gpt-5.4',
					assistant_reply_count: 3,
					operational_turn_count: 1
				},
				session: {
					...SESSIONS[0],
					available_sources: ['cli', 'json', 'state_db']
				},
				translate: (key, options) =>
					key === '{{COUNT}} replies' ? `${options?.COUNT} replies` : key === '1 op' ? '1 op' : key
			})
		).toBe('1 op • 3 replies • CLI · State DB · JSON');
	});
});

describe('groupHermesSessionsByTimeRange', () => {
	test('groups consecutive sessions by their time range while preserving order', () => {
		expect(groupHermesSessionsByTimeRange(SESSIONS)).toEqual([
			{ label: 'Today', items: [SESSIONS[0]] },
			{ label: 'Yesterday', items: [SESSIONS[1], SESSIONS[2]] }
		]);
	});

	test('falls back to Earlier when time range is missing', () => {
		expect(
			groupHermesSessionsByTimeRange([
				{ ...SESSIONS[0], time_range: '' },
				{ ...SESSIONS[2], time_range: null }
			])
		).toEqual([
			{
				label: 'Earlier',
				items: [
					{ ...SESSIONS[0], time_range: '' },
					{ ...SESSIONS[2], time_range: null }
				]
			}
		]);
	});
});

describe('getHermesSessionActivityLabel', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	test('falls back to Recently when updated_at is missing', () => {
		expect(getHermesSessionActivityLabel(null)).toEqual({ key: 'Recently' });
	});

	test('formats today activity with the existing translation key contract', () => {
		const now = new Date(2026, 3, 10, 15, 30, 0);
		const updatedAt = Math.floor(new Date(2026, 3, 10, 9, 5, 0).getTime() / 1000);

		vi.useFakeTimers();
		vi.setSystemTime(now);

		expect(getHermesSessionActivityLabel(updatedAt)).toEqual({
			key: 'Today at {{LOCALIZED_TIME}}',
			values: {
				LOCALIZED_TIME: dayjs(updatedAt * 1000).format('LT'),
				LOCALIZED_DATE: dayjs(updatedAt * 1000).format('L')
			}
		});
	});

	test('formats yesterday activity with the existing translation key contract', () => {
		const now = new Date(2026, 3, 10, 15, 30, 0);
		const updatedAt = Math.floor(new Date(2026, 3, 9, 18, 20, 0).getTime() / 1000);

		vi.useFakeTimers();
		vi.setSystemTime(now);

		expect(getHermesSessionActivityLabel(updatedAt)).toEqual({
			key: 'Yesterday at {{LOCALIZED_TIME}}',
			values: {
				LOCALIZED_TIME: dayjs(updatedAt * 1000).format('LT'),
				LOCALIZED_DATE: dayjs(updatedAt * 1000).format('L')
			}
		});
	});

	test('formats older activity with the existing localized date and time contract', () => {
		const now = new Date(2026, 3, 10, 15, 30, 0);
		const updatedAt = Math.floor(new Date(2026, 3, 7, 11, 45, 0).getTime() / 1000);

		vi.useFakeTimers();
		vi.setSystemTime(now);

		expect(getHermesSessionActivityLabel(updatedAt)).toEqual({
			key: '{{LOCALIZED_DATE}} at {{LOCALIZED_TIME}}',
			values: {
				LOCALIZED_TIME: dayjs(updatedAt * 1000).format('LT'),
				LOCALIZED_DATE: dayjs(updatedAt * 1000).format('L')
			}
		});
	});
});

describe('Hermes chat context helpers', () => {
	const translate = (key: string, options?: Record<string, number>) =>
		Object.entries(options ?? {}).reduce(
			(result, [token, value]) => result.replaceAll(`{{${token}}}`, String(value)),
			key
		);

	test('formats Hermes source labels for calm technical chips', () => {
		expect(formatHermesSourceLabel('cli')).toBe('CLI');
		expect(formatHermesSourceLabel('json')).toBe('JSON');
		expect(formatHermesSourceLabel('state_db')).toBe('State DB');
		expect(formatHermesSourceLabel('webui')).toBe('WebUI');
		expect(formatHermesSourceLabel('custom_source')).toBe('custom_source');
		expect(formatHermesSourceLabels(['json', 'state_db', 'json', 'webui'])).toEqual([
			'WebUI',
			'State DB',
			'JSON'
		]);
		expect(
			formatHermesSourceLabels(['json', 'state_db', 'json', 'webui', 'custom_source'])
		).toEqual(['WebUI', 'State DB', 'JSON', 'custom_source']);
	});

	test('formats session provenance with the canonical source first', () => {
		expect(
			getHermesSessionSourceLabels({
				...SESSIONS[0],
				source_tag: 'cli',
				available_sources: ['json', 'state_db', 'webui', 'json']
			})
		).toEqual(['CLI', 'WebUI', 'State DB', 'JSON']);

		expect(
			formatHermesSessionSourceLine({
				...SESSIONS[2],
				source_tag: 'state_db',
				available_sources: ['json', 'state_db']
			})
		).toBe('State DB · JSON');
	});

	test('reads Hermes chat meta from chat meta payload', () => {
		expect(
			getHermesChatMeta({
				hermes: {
					session_id: 'session-123',
					profile: 'default',
					source_tag: 'cli'
				}
			})
		).toEqual({
			session_id: 'session-123',
			profile: 'default',
			source_tag: 'cli'
		});
	});

	test('falls back to chat payload Hermes session metadata when meta is absent', () => {
		expect(
			resolveHermesChatMeta(null, {
				hermesSession: {
					session_id: 'session-456',
					profile: 'work',
					source_tag: 'cli'
				}
			})
		).toEqual({
			session_id: 'session-456',
			profile: 'work',
			source_tag: 'cli'
		});
	});

	test('formats Hermes context labels for calm and detailed surfaces', () => {
		const meta = { session_id: 'session-123', profile: 'default', source_tag: 'cli' };

		expect(formatHermesContextLabel(meta)).toBe('Hermes');
		expect(formatHermesContextLabel(meta, { includeCliSource: true })).toBe('Hermes • CLI');
		expect(getHermesContextBadges(meta)).toEqual(['Hermes']);
		expect(getHermesContextBadges(meta, { includeBaseLabel: false })).toEqual([]);
		expect(
			getHermesContextBadges(meta, { includeDefaultProfile: true, includeCliSource: true })
		).toEqual(['Hermes', 'default', 'CLI']);
		expect(
			formatHermesContextLabel({
				session_id: 'session-456',
				profile: 'work',
				source_tag: 'json'
			})
		).toBe('Hermes • work • JSON');
		expect(
			getHermesContextBadges({
				session_id: 'session-456',
				profile: 'work',
				source_tag: 'json'
			})
		).toEqual(['Hermes', 'work', 'JSON']);
		expect(
			getHermesContextBadges(
				{
					session_id: 'session-456',
					profile: 'work',
					source_tag: 'json'
				},
				{ includeBaseLabel: false }
			)
		).toEqual(['work', 'JSON']);
	});

	test('maps model source kinds and scoped counts for context UI copy', () => {
		expect(getHermesModelSourceLabelKey('session')).toBe('Pinned in session context');
		expect(getHermesModelSourceLabelKey('profile')).toBe('Inherited from active Hermes profile');
		expect(getHermesModelSourceLabelKey('fallback')).toBe('Browser fallback only');
		expect(getHermesModelSourceLabelKey('unknown')).toBe('Model source unknown');

		expect(formatHermesScopedCount('Visible in workspace', 12, translate)).toBe(
			'Visible in workspace: 12'
		);
		expect(formatHermesScopedCount('Visible in workspace', null, translate)).toBe('');
	});

	test('builds and formats current-session summaries from assistant activity', () => {
		const summary = buildHermesSessionSummaryFromMessages([
			{ role: 'user', content: 'hello' },
			{ role: 'assistant', model: 'openai/gpt-5.4', content: 'one' },
			{ role: 'assistant', model: 'openai/gpt-5.4', statusHistory: [{ type: 'status' }] }
		]);

		expect(summary).toEqual({
			latest_assistant_model: 'openai/gpt-5.4',
			assistant_reply_count: 2,
			operational_turn_count: 1
		});
		expect(formatHermesSessionMetaLine(summary, translate)).toBe('gpt-5.4 • 1 op • 2 replies');
		expect(formatHermesSessionMetaLine(null, translate)).toBe('');
		expect(
			formatHermesChatListMetaLine({
				hermesMeta: {
					session_id: 'session-123',
					profile: 'default',
					source_tag: 'cli'
				},
				summary,
				translate
			})
		).toBe('Hermes • CLI • 1 op • 2 replies');
		expect(
			formatHermesChatListMetaLine({
				hermesMeta: {
					session_id: 'session-imported',
					profile: 'work',
					source_tag: 'cli'
				},
				session: {
					...SESSIONS[1],
					source_tag: 'cli',
					available_sources: ['cli', 'json', 'state_db'],
					is_auxiliary_cli_session: true
				},
				summary,
				translate
			})
		).toBe('Hermes • work • Auxiliary • 1 op • 2 replies • CLI · State DB · JSON');
	});
});
