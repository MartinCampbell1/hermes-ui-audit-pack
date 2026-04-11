<script lang="ts">
	import { getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { getChatList, getPinnedChatList } from '$lib/apis/chats';
	import {
		importHermesSession,
		type HermesRuntime
	} from '$lib/apis/hermes';
	import Search from '$lib/components/icons/Search.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		chats,
		currentChatPage,
		hermesRecentSessions,
		hermesSessionsByChatId,
		hermesRuntimeStore,
		pinnedChats
	} from '$lib/stores';
	import {
		buildHermesSessionSummaryFromMessages,
		countHermesSessionsByScope,
		filterHermesSessions,
		formatHermesChatSidebarMetaLine,
		formatHermesSessionSourceLine,
		formatHermesSessionMetaLine,
		getHermesContextBadges,
		getHiddenAuxiliaryHermesSessions,
		getResolvedHermesSessionContext,
		isCurrentHermesSession,
		getHermesSessionActivityLabel,
		groupHermesSessionsByTimeRange,
		refreshHermesSessionStores,
		type HermesSessionListItem,
		type HermesSessionScope
	} from '$lib/utils/hermesSessions';
	import { ensureHermesContextBundle } from '$lib/utils/hermesContext';

	const i18n = getContext<any>('i18n');

	// TODO(21st): Replace this stopgap local panel pattern with a 21st.dev-derived micro-surface once MCP auth is fixed.

	export let active = false;
	export let chatId: string | null = null;
	export let chatHermesSession: Record<string, any> | null = null;
	export let chatMeta: Record<string, any> | null = null;
	export let history = {};
	export let models: any[] = [];
	export let taskIds: string[] | null = null;
	export let chatFiles: any[] = [];
	export let mode: 'context' | 'history' = 'context';

	const getMessages = (history: any) => Object.values(history?.messages ?? {});

	let messages: any[] = [];
	let assistantCount = 0;
	let userCount = 0;
	let operationalTurns = 0;
	let loaded = false;
	let loading = false;
	let runtime: HermesRuntime | null = null;
	let sessions: HermesSessionListItem[] = [];
	let loadError = '';
	let importInFlightId: string | null = null;
	let openingChatId: string | null = null;
	let showAuxiliarySessions = false;
	let sessionQuery = '';
	let activeFilter: HermesSessionScope = 'all';
	let wasActive = false;
	let lastLoadedAt = 0;
	let showInspector = false;
	let sessionFilters: { id: HermesSessionScope; label: string }[] = [];

	const HERMES_SESSION_PANEL_REFRESH_TTL_MS = 10_000;

	$: messages = getMessages(history);
	$: assistantCount = messages.filter((message) => message?.role === 'assistant').length;
	$: userCount = messages.filter((message) => message?.role === 'user').length;
	$: operationalTurns = messages.filter(
		(message) =>
			message?.role === 'assistant' &&
			(!!message?.hermesApproval ||
				(message?.statusHistory?.length ?? 0) > 0 ||
				(message?.code_executions?.length ?? 0) > 0)
	).length;
	$: modelLabels = (models ?? []).map((model) => model?.name ?? model?.id).filter(Boolean);
	$: runtime = $hermesRuntimeStore;
	$: runtimeWarnings = runtime?.warnings ?? [];
	$: currentHermesMeta = getResolvedHermesSessionContext({
		session: chatHermesSession,
		meta: chatMeta,
		runtime
	});
	$: currentHermesSessionId = currentHermesMeta?.session_id ?? null;
	$: currentHermesSessionItem =
		sessions.find((session) => isCurrentSession(session)) ??
		(chatId ? $hermesSessionsByChatId[chatId] ?? null : null);
	$: auxiliarySessions = getHiddenAuxiliaryHermesSessions(sessions, {
		currentChatId: chatId,
		currentSessionId: currentHermesSessionId
	});
	$: baseVisibleSessions = showAuxiliarySessions
		? sessions
		: sessions.filter((session) => !auxiliarySessions.includes(session));
	$: sessionCounts = countHermesSessionsByScope(baseVisibleSessions, {
		currentChatId: chatId,
		currentSessionId: currentHermesSessionId
	});
	$: sessionFilters = [
		{ id: 'all', label: $i18n.t('All') },
		...(sessionCounts.imported > 0 ? [{ id: 'imported', label: $i18n.t('Imported') }] : []),
		...(sessionCounts.current > 0 ? [{ id: 'current', label: $i18n.t('Current chat') }] : [])
	] as { id: HermesSessionScope; label: string }[];
	$: if (!sessionFilters.some((filter) => filter.id === activeFilter)) {
		activeFilter = 'all';
	}
	$: hasSessionNarrowing = activeFilter !== 'all' || sessionQuery.trim().length > 0;
	$: visibleSessions = filterHermesSessions(baseVisibleSessions, {
		query: sessionQuery,
		scope: activeFilter,
		currentChatId: chatId,
		currentSessionId: currentHermesSessionId
	});
	$: groupedVisibleSessions = groupHermesSessionsByTimeRange(visibleSessions);
	$: currentHermesSummary = buildHermesSessionSummaryFromMessages(messages);
	$: currentHermesSummaryLine = currentHermesSessionItem
		? formatHermesChatSidebarMetaLine({
				summary: currentHermesSummary,
				session: currentHermesSessionItem,
				translate: $i18n.t
			})
		: formatHermesSessionMetaLine(currentHermesSummary, $i18n.t);
	$: currentHermesSourceLine =
		currentHermesSessionItem && formatHermesSessionSourceLine(currentHermesSessionItem);
	$: currentHermesContextItems = [
		currentHermesSummaryLine,
		currentHermesSourceLine && currentHermesSourceLine !== currentHermesSummaryLine
			? currentHermesSourceLine
			: null
	].filter(Boolean);
	$: currentHermesModelLabel =
		formatModelLabel(currentHermesSessionItem?.model ?? currentHermesMeta?.model) ||
		formatModelLabel(currentHermesSummary?.latest_assistant_model);
	$: browserFallbackModelLabel = modelLabels.at(0) ?? '';
	$: currentHermesModelSourceKind = currentHermesSessionItem?.imported_chat_id
		? 'session'
		: currentHermesMeta?.profile
			? 'profile'
			: runtime?.active_profile
				? 'runtime'
				: 'browser';
	$: currentHermesModelSourceLabel =
		currentHermesModelSourceKind === 'session'
			? $i18n.t('Imported session context')
			: currentHermesModelSourceKind === 'profile'
				? $i18n.t('Active Hermes profile')
				: currentHermesModelSourceKind === 'runtime'
					? $i18n.t('Current runtime')
					: $i18n.t('Browser fallback only');
	$: runtimeDiffersFromSession =
		!!currentHermesMeta?.profile &&
		!!runtime?.active_profile &&
		currentHermesMeta.profile !== runtime.active_profile;
	$: currentHermesModelSourceDetail =
		currentHermesModelSourceKind === 'session'
			? runtimeDiffersFromSession
				? $i18n.t('Imported session context differs from the active Hermes runtime.')
				: $i18n.t('Pinned in session context')
			: currentHermesModelSourceKind === 'profile'
				? $i18n.t('Inherited from active Hermes profile')
				: currentHermesModelSourceKind === 'runtime'
					? $i18n.t('Active Hermes runtime')
					: $i18n.t('Open WebUI fallback only; Hermes uses the active profile model above.');

	const formatModelLabel = (modelId: string | null | undefined) => {
		if (!modelId) return '';
		return modelId.split('/').pop() ?? modelId;
	};

	const isCurrentSession = (session: HermesSessionListItem) =>
		isCurrentHermesSession(session, {
			currentChatId: chatId,
			currentSessionId: currentHermesSessionId
		});

	const getSessionStatusLabel = (session: HermesSessionListItem) => {
		if (isCurrentSession(session)) {
			return $i18n.t('Attached to chat');
		}

		if (session.imported_chat_archived) {
			return $i18n.t('Archived');
		}

		if (session.imported_chat_id) {
			return $i18n.t('Imported');
		}

		return '';
	};

	const getSessionActionLabel = (session: HermesSessionListItem) => {
		if (importInFlightId === session.session_id) {
			return `${$i18n.t('Importing')}...`;
		}

		if (session.imported_chat_id && openingChatId === session.imported_chat_id) {
			return `${$i18n.t('Opening')}...`;
		}

		if (isCurrentSession(session)) {
			return $i18n.t('Attached to chat');
		}

		if (session.imported_chat_archived) {
			return $i18n.t('Open archived');
		}

		if (session.imported_chat_id) {
			return $i18n.t('Open existing');
		}

		return $i18n.t('Import and open');
	};

	const formatSessionActivityLabel = (session: HermesSessionListItem) => {
		const activityLabel = getHermesSessionActivityLabel(session.updated_at);

		return $i18n.t(activityLabel.key, activityLabel.values ?? {});
	};

	const getSessionContextBadges = (session: HermesSessionListItem) => {
		return getHermesContextBadges(
			{
				session_id: session.session_id,
				profile: session.profile,
				source_tag: null
			},
			{ includeBaseLabel: false }
		);
	};

	const getSessionSourceLine = (session: HermesSessionListItem) =>
		formatHermesSessionSourceLine(session);
	const shouldShowSessionSecondaryDetails = (session: HermesSessionListItem) =>
		isCurrentSession(session) || !!session.imported_chat_id || sessionQuery.trim().length > 0;
	const getVisibleSessionContextBadges = (session: HermesSessionListItem) =>
		getSessionContextBadges(session).slice(0, 2);

	const refreshChatStores = async () => {
		currentChatPage.set(1);
		await chats.set(await getChatList(localStorage.token, 1));
		await pinnedChats.set(await getPinnedChatList(localStorage.token));
	};

	const getErrorMessage = (error: any, fallback: string) => {
		if (typeof error === 'string') {
			return error;
		}

		return error?.detail ?? error?.message ?? fallback;
	};

	const openChat = async (nextChatId: string) => {
		await refreshChatStores();
		await goto(`/c/${nextChatId}`);
	};

	const handleOpenExisting = async (session: HermesSessionListItem) => {
		if (!session.imported_chat_id || openingChatId || importInFlightId) {
			return;
		}

		openingChatId = session.imported_chat_id;

		try {
			await openChat(session.imported_chat_id);
			toast.success(
				session.imported_chat_archived
					? $i18n.t('Opened archived Hermes session.')
					: $i18n.t('Opened existing Hermes session.')
			);
		} catch (error) {
			toast.error(getErrorMessage(error, $i18n.t('Failed to open Hermes session.')));
		} finally {
			openingChatId = null;
		}
	};

	const loadSessions = async (force = false) => {
		if (loading || (loaded && !force)) {
			return;
		}

		loading = true;
		loadError = '';

		const [_, sessionsRes] = await Promise.all([
			ensureHermesContextBundle(localStorage.token, {
				force,
				includeProfiles: false
			}),
			refreshHermesSessionStores(localStorage.token).catch((error) => {
				console.error(error);
				return null;
			})
		]);

		sessions = sessionsRes ?? [];
		if (!sessionsRes) {
			loadError = $i18n.t('Failed to load Hermes sessions.');
		}

		if (!runtime && !sessionsRes) {
			loadError = $i18n.t('Failed to load Hermes sessions.');
		}

		loaded = true;
		lastLoadedAt = Date.now();
		loading = false;
	};

	const handleImport = async (sessionId: string) => {
		if (importInFlightId) {
			return;
		}

		importInFlightId = sessionId;

		try {
			const res = await importHermesSession(localStorage.token, sessionId).catch((error) => {
				toast.error(getErrorMessage(error, $i18n.t('Failed to import Hermes session.')));
				return null;
			});

			if (res?.chat?.id) {
				await loadSessions(true);
				await openChat(res.chat.id);
				toast.success(
					res.already_imported
						? $i18n.t('Opened existing Hermes session.')
						: $i18n.t('Hermes session imported.')
				);
			}
		} catch (error) {
			toast.error(getErrorMessage(error, $i18n.t('Failed to open Hermes session.')));
		} finally {
			importInFlightId = null;
		}
	};

	$: if (active && !wasActive) {
		const shouldRefresh =
			!loaded || Date.now() - lastLoadedAt > HERMES_SESSION_PANEL_REFRESH_TTL_MS;
		wasActive = true;
		if (shouldRefresh && !loading) {
			loadSessions(true);
		}
	}

	$: if (!active && wasActive) {
		wasActive = false;
	}

	$: if (
		active &&
		loaded &&
		!loading &&
		($hermesRecentSessions.length > 0 || sessions.length > 0)
	) {
		sessions = $hermesRecentSessions;
	}
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	{#if mode === 'context'}
		<div
			class="rounded-xl border border-gray-100/80 bg-white/80 px-4 py-4 dark:border-gray-800/80 dark:bg-gray-900/50"
		>
			<div class="flex items-start justify-between gap-3">
				<div class="min-w-0">
					<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
						{$i18n.t('Current chat context')}
					</div>
					<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
						{$i18n.t('Source of truth for the live transcript, model context and attached files.')}
					</div>
				</div>
				<div
					class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-300"
				>
					{messages.length} {$i18n.t('Messages')}
				</div>
			</div>

			{#if currentHermesContextItems.length > 0}
				<div class="mt-2 flex flex-wrap gap-1.5">
					{#each currentHermesContextItems as item}
						<div
							class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
						>
							{item}
						</div>
					{/each}
				</div>
			{/if}

			<div class="mt-3 grid grid-cols-2 gap-2">
				<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
					<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
						{$i18n.t('Assistant replies')}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{assistantCount}
					</div>
				</div>

				<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
					<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
						{$i18n.t('User turns')}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{userCount}
					</div>
				</div>

				<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
					<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
						{$i18n.t('Operational turns')}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{operationalTurns}
					</div>
				</div>

				<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
					<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
						{$i18n.t('Attached to chat')}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{chatFiles.length}
					</div>
				</div>
			</div>

			<div class="mt-3 rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
				<div class="flex items-center justify-between gap-3">
					<div class="min-w-0">
						<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
							{$i18n.t('Model context')}
						</div>
						<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
							{currentHermesModelSourceDetail}
						</div>
					</div>
					<div
						class="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-900/70 dark:text-gray-300"
					>
						{$i18n.t('Tasks')} · {taskIds?.length ?? 0}
					</div>
				</div>

				<div class="mt-2 flex flex-wrap gap-1.5">
					<div
						class="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-900/70 dark:text-gray-300"
					>
						{$i18n.t('Active model')}: {currentHermesModelLabel || $i18n.t('Not set')}
					</div>
					<div
						class="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-900/70 dark:text-gray-300"
					>
						{$i18n.t('Model source')}: {currentHermesModelSourceLabel}
					</div>
					<div
						class="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-900/70 dark:text-gray-300"
					>
						{$i18n.t('Browser fallback')}: {browserFallbackModelLabel || $i18n.t('Not set')}
					</div>
				</div>
			</div>
		</div>

		<div class="mt-2 flex flex-col gap-1.5 px-1 pb-2">
			<div
				class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
			>
				<div class="flex items-center justify-between gap-3">
					<div class="min-w-0">
						<div
							class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
						>
							{$i18n.t('Active Hermes runtime')}
						</div>
						<div class="mt-1 text-sm text-gray-700 dark:text-gray-200">
							{runtime?.active_profile ?? $i18n.t('Default profile')}
						</div>
						{#if runtimeDiffersFromSession}
							<div class="mt-1 text-[11px] text-amber-600 dark:text-amber-400">
								{$i18n.t('Imported session context uses a different Hermes profile.')}
							</div>
						{/if}
					</div>
					<div class="flex items-center gap-1.5">
						<button
							type="button"
							class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
							on:click={() => {
								showInspector = !showInspector;
							}}
						>
							{$i18n.t(showInspector ? 'Hide inspector' : 'Show inspector')}
						</button>
						<button
							type="button"
							class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
							on:click={() => {
								loaded = false;
								loadSessions(true);
							}}
						>
							{$i18n.t('Refresh')}
						</button>
					</div>
				</div>

				{#if showInspector}
					{#if loading && !loaded}
						<div class="mt-3 flex h-10 items-center justify-center">
							<Spinner className="size-4" />
						</div>
					{:else if runtime}
						<div class="mt-2 flex flex-col gap-1.5 text-xs text-gray-500 dark:text-gray-400">
							<div class="line-clamp-1">{$i18n.t('Home directory')}: {runtime.active_home}</div>
							<div class="line-clamp-1">
								{$i18n.t('Agent')}: {runtime.agent_dir ?? $i18n.t('Not found')}
							</div>
							<div class="line-clamp-1">{$i18n.t('Python')}: {runtime.python_path}</div>
						</div>
					{:else}
						<div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('Hermes runtime is unavailable.')}
						</div>
					{/if}

					{#if runtimeWarnings.length > 0}
						<div
							class="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
						>
							{#each runtimeWarnings as warning}
								<div>{warning}</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</div>
	{/if}

	{#if mode === 'history'}
		<div class="flex min-h-0 flex-1 flex-col gap-2">
			<div
				class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-3 dark:border-gray-800/80 dark:bg-gray-900/50"
			>
				<div class="flex items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
							{$i18n.t('Search Sessions')}
						</div>
						<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
							{$i18n.t('Hermes sessions stay linked to Chats. Open or import one directly.')}
						</div>
					</div>

					{#if hasSessionNarrowing}
						<button
							type="button"
							class="shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
							on:click={() => {
								sessionQuery = '';
								activeFilter = 'all';
							}}
						>
							{$i18n.t('Clear search')}
						</button>
					{/if}
				</div>

				<div class="mt-3 flex items-center gap-2">
					<div class="flex flex-1 items-center rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-900/70">
						<div class="mr-2 text-gray-400 dark:text-gray-500">
							<Search className="size-3.5" />
						</div>
						<input
							class="w-full bg-transparent text-sm outline-hidden"
							bind:value={sessionQuery}
							placeholder={$i18n.t('Search Sessions')}
						/>
					</div>
				</div>

				{#if sessionFilters.length > 1}
					<div class="mt-3 border-t border-gray-100/80 pt-3 dark:border-gray-800/80">
						<div class="mb-2 text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
							{$i18n.t('Scope')}
						</div>
						<div class="flex flex-wrap gap-1.5">
							{#each sessionFilters as filter}
								<button
									type="button"
									class="{activeFilter === filter.id
										? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
										: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'} rounded-full px-2.5 py-1 text-[11px] font-medium transition hover:bg-gray-200 dark:hover:bg-gray-700"
									on:click={() => {
										activeFilter = filter.id;
									}}
								>
									{#if filter.id === 'all'}
										{filter.label} · {sessionCounts.all}
									{:else if filter.id === 'imported'}
										{filter.label} · {sessionCounts.imported}
									{:else if filter.id === 'current'}
										{filter.label} · {sessionCounts.current}
									{/if}
								</button>
							{/each}
						</div>
					</div>
				{/if}
			</div>

			<div
				class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-gray-100/80 bg-white/80 dark:border-gray-800/80 dark:bg-gray-900/50"
			>
				<div class="flex items-center justify-between gap-3 px-3 py-3">
					<div>
						<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
							{$i18n.t('Hermes session history')}
						</div>
						<div class="text-[11px] text-gray-400 dark:text-gray-500">
							{$i18n.t('Real CLI and runtime history')} · {visibleSessions.length}
							{#if hasSessionNarrowing}
								/ {baseVisibleSessions.length}
							{:else if auxiliarySessions.length > 0 && !showAuxiliarySessions}
								/ {sessions.length}
							{/if}
						</div>
					</div>

					{#if chatId}
						<div
							class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-300"
						>
							{$i18n.t('Attached to chat')}
						</div>
					{/if}
				</div>

				{#if auxiliarySessions.length > 0}
					<div
						class="mx-3 mb-1 flex items-center justify-between gap-3 rounded-xl border border-gray-100/80 bg-gray-50/80 px-3 py-2 text-[11px] text-gray-500 dark:border-gray-800/80 dark:bg-gray-950/40 dark:text-gray-400"
					>
						<div class="min-w-0">
							{#if showAuxiliarySessions}
								{$i18n.t('Showing auxiliary and system sessions alongside the main history.')}
							{:else}
								{auxiliarySessions.length} {$i18n.t('auxiliary or system sessions are hidden by default.')}
							{/if}
						</div>

						<button
							type="button"
							class="shrink-0 rounded-full bg-white px-2.5 py-1 font-medium text-gray-600 transition hover:bg-gray-100 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
							on:click={() => {
								showAuxiliarySessions = !showAuxiliarySessions;
							}}
						>
							{#if showAuxiliarySessions}
								{$i18n.t('Hide auxiliary')}
							{:else}
								{$i18n.t('Show hidden')} · {auxiliarySessions.length}
							{/if}
						</button>
					</div>
				{/if}

				<div class="flex-1 min-h-0 overflow-y-auto px-1 pb-2">
					{#if loading && !loaded}
						<div class="flex h-24 items-center justify-center">
							<Spinner className="size-4" />
						</div>
					{:else if loadError}
						<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
							{loadError}
						</div>
					{:else if sessions.length === 0}
						<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
							{$i18n.t('No Hermes sessions found.')}
						</div>
					{:else if visibleSessions.length === 0}
						<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
							{#if hasSessionNarrowing}
								{$i18n.t('No Hermes sessions match the current search or filters.')}
							{:else}
								{$i18n.t('Only auxiliary or system sessions are available right now.')}
							{/if}
						</div>
					{:else}
						<div class="flex flex-col gap-1.5">
							{#each groupedVisibleSessions as group, groupIndex (group.label)}
								<div
									class="px-2 pb-1 text-xs font-medium text-gray-400 dark:text-gray-500 {groupIndex ===
									0
										? ''
										: 'pt-4'}"
								>
									{$i18n.t(group.label)}
									<!-- localisation keys for time_range to be recognized from the i18next parser:
										{$i18n.t('Today')}
										{$i18n.t('Yesterday')}
										{$i18n.t('Previous 7 days')}
										{$i18n.t('Previous 30 days')}
										{$i18n.t('January')}
										{$i18n.t('February')}
										{$i18n.t('March')}
										{$i18n.t('April')}
										{$i18n.t('May')}
										{$i18n.t('June')}
										{$i18n.t('July')}
										{$i18n.t('August')}
										{$i18n.t('September')}
										{$i18n.t('October')}
										{$i18n.t('November')}
										{$i18n.t('December')}
										{$i18n.t('Earlier')}
									-->
								</div>

								{#each group.items as session (session.session_id)}
									<div
										class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
									>
										<div class="flex flex-col gap-2">
											<div class="min-w-0">
												<div class="flex flex-wrap items-center gap-2">
													<div
														class="min-w-0 flex-1 line-clamp-1 text-sm font-medium text-gray-800 dark:text-gray-100"
													>
														{session.title}
													</div>
													{#if getSessionStatusLabel(session)}
														<div
															class="shrink-0 whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300"
														>
															{getSessionStatusLabel(session)}
														</div>
													{/if}
													{#if session.is_auxiliary_cli_session}
														<div
															class="shrink-0 whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-300"
														>
															{$i18n.t('Auxiliary')}
														</div>
													{/if}
													<div
														class="shrink-0 whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-300"
													>
														{formatModelLabel(session.model) || $i18n.t('Unknown')}
													</div>
												</div>

												<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
													{formatSessionActivityLabel(session)} · {session.message_count}
													{$i18n.t('Messages')}
												</div>

												{#if shouldShowSessionSecondaryDetails(session) && session.last_user_content}
													<div
														class="mt-1 line-clamp-1 text-xs leading-5 text-gray-500 dark:text-gray-400"
													>
														{session.last_user_content}
													</div>
												{/if}

												{#if shouldShowSessionSecondaryDetails(session) && getSessionSourceLine(session)}
													<div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
														{getSessionSourceLine(session)}
													</div>
												{/if}

												{#if shouldShowSessionSecondaryDetails(session) && getVisibleSessionContextBadges(session).length > 0}
													<div class="mt-2 flex flex-wrap gap-1.5">
														{#each getVisibleSessionContextBadges(session) as badge}
															<div
																class="shrink-0 whitespace-nowrap rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-300"
															>
																{badge}
															</div>
														{/each}
													</div>
												{/if}
											</div>

											<div class="flex justify-start">
												<button
													type="button"
													class="max-w-full whitespace-nowrap rounded-full bg-gray-900 px-2.5 py-1 text-[11px] font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
													on:click={async () => {
														if (isCurrentSession(session)) {
															return;
														}

														if (session.imported_chat_id) {
															await handleOpenExisting(session);
															return;
														}

														handleImport(session.session_id);
													}}
													disabled={importInFlightId !== null ||
														openingChatId !== null ||
														isCurrentSession(session)}
												>
													{getSessionActionLabel(session)}
												</button>
											</div>
										</div>
									</div>
								{/each}
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
