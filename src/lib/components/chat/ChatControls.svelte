<script context="module" lang="ts">
	let savedTab:
		| 'controls'
		| 'files'
		| 'history'
		| 'overview'
		| 'session'
		| 'profile'
		| 'skills'
		| 'memory'
		| 'tasks'
		| 'todos' = 'session';
</script>

<script lang="ts">
	import { SvelteFlowProvider } from '@xyflow/svelte';
	import { slide } from 'svelte/transition';
	import { Pane, PaneResizer, type PaneAPI } from 'paneforge';
	import { onDestroy, onMount, tick, getContext } from 'svelte';
	import {
		chatControlsOpenTarget,
		config,
		hermesContextLoaded,
		hermesContextLoading,
		hermesProfilesLoaded,
		hermesProfilesLoading,
		hermesProfilesStore,
		hermesRuntimeStore,
		hermesWorkspacesStore,
		terminalServers,
		mobile,
		showControls,
		showCallOverlay,
		showArtifacts,
		showEmbeds,
		settings,
		showFileNavPath,
		selectedTerminalId,
		temporaryChatEnabled,
		user,
		type WorkspacePanelStatus
	} from '$lib/stores';

	import { uploadFile } from '$lib/apis/files';
	import type { HermesWorkspacesResponse } from '$lib/apis/hermes';
	import { toast } from 'svelte-sonner';
	import { collectHermesGeneratedWorkspaceFiles } from '$lib/utils/hermesWorkspace';
	import { buildHermesContextSummary, ensureHermesContextBundle } from '$lib/utils/hermesContext';

	import Controls from './Controls/Controls.svelte';
	import CallOverlay from './MessageInput/CallOverlay.svelte';
	import Drawer from '../common/Drawer.svelte';
	import Artifacts from './Artifacts.svelte';
	import Embeds from './ChatControls/Embeds.svelte';
	import FileNav from './FileNav.svelte';
	import PyodideFileNav from './PyodideFileNav.svelte';
	import Overview from './Overview.svelte';
	import HermesContextBar from '$lib/components/hermes/context/HermesContextBar.svelte';
	import HermesWorkspaceHeader from '$lib/components/hermes/workspace/HermesWorkspaceHeader.svelte';
	import HermesWorkspaceStub from '$lib/components/hermes/workspace/HermesWorkspaceStub.svelte';
	import HermesSessionPanel from '$lib/components/hermes/panels/HermesSessionPanel.svelte';
	import HermesProfilePanel from '$lib/components/hermes/panels/HermesProfilePanel.svelte';
	import HermesSkillsPanel from '$lib/components/hermes/panels/HermesSkillsPanel.svelte';
	import HermesMemoryPanel from '$lib/components/hermes/panels/HermesMemoryPanel.svelte';
	import HermesTasksPanel from '$lib/components/hermes/panels/HermesTasksPanel.svelte';
	import HermesTodosPanel from '$lib/components/hermes/panels/HermesTodosPanel.svelte';
	import { getResolvedHermesSessionContext } from '$lib/utils/hermesSessions';

	const i18n = getContext<any>('i18n');
	const HERMES_OPERATOR_MODE = true;
	type PanelTabId =
		| 'controls'
		| 'files'
		| 'history'
		| 'overview'
		| 'session'
		| 'profile'
		| 'skills'
		| 'memory'
		| 'tasks'
		| 'todos';
	type PanelTab = {
		id: PanelTabId;
		label: string;
	};

	export let history: Record<string, any> = {};
	export let models: any[] = [];

	export let chatId: string | null = null;
	export let chatHermesSession: Record<string, any> | null = null;
	export let chatMeta: Record<string, any> | null = null;

	export let chatFiles: any[] = [];
	export let params: Record<string, any> = {};

	export let eventTarget: EventTarget;
	export let submitPrompt: Function;
	export let stopResponse: Function;
	export let showMessage: Function;
	export let files: any[] = [];
	export let modelId: string | null = null;
	export let taskIds: string[] | null = null;
	export let hermesStreamActive = false;

	export let codeInterpreterEnabled = false;
	export let onHermesProfileSwitched: (
		payload?: Record<string, any> | null
	) => void | Promise<void> = () => {};

	export let pane: PaneAPI | undefined = undefined;

	let largeScreen = false;
	let dragged = false;
	let minSize = 0;
	let paneReady = false;
	let sessionTabPinned = false;
	let inspectTabsExpanded = false;
	let activeWorkspaceSource: WorkspacePanelStatus['source'] = 'stub';
	let defaultWorkspaceStatus: WorkspacePanelStatus = {
		source: 'stub',
		currentPath: undefined,
		itemCount: undefined,
		visibleItemCount: undefined,
		linkedItemCount: undefined,
		selectedFile: null,
		selectedFileName: null,
		attachEnabled: false
	};
	let effectiveWorkspaceStatus: WorkspacePanelStatus = defaultWorkspaceStatus;

	// Tab state for Controls+Workspace panel
	let activeTab: PanelTabId = savedTab;
	// svelte-ignore reactive_declaration_module_script_dependency
	$: {
		savedTab = activeTab;
	}

	let hasMessages = false;
	let primaryTabs: PanelTab[] = [];
	let inspectTabs: PanelTab[] = [];
	let activeTabInInspectGroup = false;
	let showPrimaryContextSummary = false;
	let showInspectContextSummary = false;

	$: hasMessages = !!(history?.messages && Object.keys(history.messages).length > 0);
	$: currentHermesMeta = getResolvedHermesSessionContext({
		session: chatHermesSession,
		meta: chatMeta,
		runtime: $hermesRuntimeStore
	});
	$: showAdvancedTab = HERMES_OPERATOR_MODE
		? $user?.role === 'admin'
		: $user?.role === 'admin' || ($user?.permissions?.chat?.controls ?? true);
	$: if ($chatControlsOpenTarget === 'session') {
		sessionTabPinned = true;
	}
	$: if (!$showControls && !hasMessages) {
		sessionTabPinned = false;
	}
	$: showSessionTab = true;
	$: showProfileTab = !!$user;
	$: showSkillsTab = $user?.role === 'admin' || ($user?.permissions?.workspace?.skills ?? false);
	$: showMemoryTab =
		$config?.features?.enable_memories &&
		($user?.role === 'admin' || ($user?.permissions?.features?.memories ?? true));
	$: showTasksTab = hasMessages || taskIds !== null;
	$: showTodosTab = hasMessages;
	$: showFilesTab = true;
	$: showOverviewTab = hasMessages;
	$: primaryTabs = [
		...(showSessionTab ? [{ id: 'session', label: $i18n.t('Context') }] : []),
		...(showSessionTab ? [{ id: 'history', label: $i18n.t('Sessions') }] : []),
		...(showFilesTab ? [{ id: 'files', label: $i18n.t('Workspace') }] : []),
		...(showTasksTab ? [{ id: 'tasks', label: $i18n.t('Tasks') }] : [])
	] as PanelTab[];
	$: inspectTabs = [
		...(showProfileTab ? [{ id: 'profile', label: $i18n.t('Profile') }] : []),
		...(showSkillsTab ? [{ id: 'skills', label: $i18n.t('Skills') }] : []),
		...(showMemoryTab ? [{ id: 'memory', label: $i18n.t('Memory') }] : []),
		...(showOverviewTab ? [{ id: 'overview', label: $i18n.t('Overview') }] : []),
		...(showTodosTab ? [{ id: 'todos', label: $i18n.t('Todos') }] : []),
		...(showAdvancedTab ? [{ id: 'controls', label: $i18n.t('Advanced') }] : [])
	] as PanelTab[];
	$: activeTabInInspectGroup = inspectTabs.some((tab) => tab.id === activeTab);
	$: showPrimaryContextSummary =
		!!panelContextSummary &&
		activeTab !== 'overview' &&
		activeTab !== 'session' &&
		activeTab !== 'history' &&
		activeTab !== 'files' &&
		!activeTabInInspectGroup;
	$: showInspectContextSummary =
		!!panelContextSummary && activeTab !== 'overview' && activeTabInInspectGroup;
	$: if (activeTabInInspectGroup) {
		inspectTabsExpanded = true;
	}
	$: if (!activeTabInInspectGroup && inspectTabs.length === 0) {
		inspectTabsExpanded = false;
	}
	let workspaceStatus: WorkspacePanelStatus | null = null;

	$: activeWorkspaceSource = $selectedTerminalId
		? 'terminal'
		: codeInterpreterEnabled
			? 'pyodide'
			: 'stub';
	$: generatedWorkspaceFiles = collectHermesGeneratedWorkspaceFiles(history);
	$: stubWorkspaceItemCount = (chatFiles?.length ?? 0) + generatedWorkspaceFiles.length;
	$: defaultWorkspaceStatus = {
		source: activeWorkspaceSource,
		currentPath: undefined,
		itemCount: activeWorkspaceSource === 'stub' ? stubWorkspaceItemCount : undefined,
		visibleItemCount: undefined,
		linkedItemCount: activeWorkspaceSource === 'stub' ? stubWorkspaceItemCount : undefined,
		selectedFile: null,
		selectedFileName: null,
		attachEnabled: false
	} satisfies WorkspacePanelStatus;
	$: effectiveWorkspaceStatus =
		workspaceStatus?.source === activeWorkspaceSource
			? {
					...defaultWorkspaceStatus,
					...workspaceStatus,
					itemCount: workspaceStatus.itemCount ?? defaultWorkspaceStatus.itemCount
				}
			: defaultWorkspaceStatus;
	$: activeHermesWorkspaceItem = $hermesWorkspacesStore?.items?.find((item) => item.is_active) ?? null;
	$: activeHermesWorkspaceName = activeHermesWorkspaceItem?.name ?? '';
	$: activeHermesWorkspacePath = activeHermesWorkspaceItem?.path ?? '';
	$: workspaceTitle =
		activeHermesWorkspaceName ||
		($selectedTerminalId
			? $i18n.t('Terminal workspace')
			: codeInterpreterEnabled
				? $i18n.t('Code workspace')
				: $i18n.t('Workspace'));
	$: workspaceSubtitle = $selectedTerminalId
		? $i18n.t('Browse, preview, and attach files for the current conversation.')
		: codeInterpreterEnabled
			? $i18n.t('Inspect runtime files created during this session.')
			: $i18n.t('Inspect the active Hermes workspace and files attached to this chat.');
	$: workspaceBadge = $selectedTerminalId
		? $i18n.t('Terminal')
		: codeInterpreterEnabled
			? $i18n.t('Local')
			: $i18n.t('Hermes');
	$: workspacePathLabel = effectiveWorkspaceStatus.currentPath
		? $i18n.t('Path: {{PATH}}', { PATH: effectiveWorkspaceStatus.currentPath })
		: activeHermesWorkspacePath
			? $i18n.t('Path: {{PATH}}', { PATH: activeHermesWorkspacePath })
			: activeWorkspaceSource === 'stub'
				? $i18n.t('Chat files only')
				: $i18n.t('No active directory');
	$: workspaceVisibleItemCount =
		typeof effectiveWorkspaceStatus.visibleItemCount === 'number'
			? effectiveWorkspaceStatus.visibleItemCount
			: activeWorkspaceSource !== 'stub' && typeof effectiveWorkspaceStatus.itemCount === 'number'
				? effectiveWorkspaceStatus.itemCount
				: null;
	$: workspaceItemCountLabel =
		typeof workspaceVisibleItemCount === 'number'
			? $i18n.t('Visible items: {{COUNT}}', {
					COUNT: workspaceVisibleItemCount
				})
			: '';
	$: workspaceSelectionLabel = effectiveWorkspaceStatus.selectedFileName
		? $i18n.t('Previewing {{NAME}}', { NAME: effectiveWorkspaceStatus.selectedFileName })
		: '';
	$: workspaceMetaItems = [workspacePathLabel, workspaceItemCountLabel, workspaceSelectionLabel].filter(
		Boolean
	);
	$: panelContextSummary = buildHermesContextSummary({
		chatHermesSession,
		chatMeta,
		runtime: $hermesRuntimeStore,
		workspaces: $hermesWorkspacesStore,
		profiles: $hermesProfilesStore,
		workspaceStatus: effectiveWorkspaceStatus,
		temporaryChatEnabled: $temporaryChatEnabled,
		currentMessageId: history?.currentId,
		selectedModelLabel: models?.[0]?.name ?? modelId ?? '',
		generatedFileCount: generatedWorkspaceFiles.length,
		chatAttachedFileCount: chatFiles?.length ?? 0,
		taskCount: taskIds?.length ?? 0
	});
	$: panelStats = [
		typeof panelContextSummary.workspaceVisibleCount === 'number'
			? {
					label: $i18n.t('Workspace'),
					value: panelContextSummary.workspaceVisibleCount
				}
			: null,
		typeof panelContextSummary.chatAttachedFileCount === 'number'
			? {
					label: $i18n.t('Attached'),
					value: panelContextSummary.chatAttachedFileCount
				}
			: null,
		typeof panelContextSummary.generatedFileCount === 'number'
			? {
					label: $i18n.t('Generated'),
					value: panelContextSummary.generatedFileCount
				}
			: null,
		typeof panelContextSummary.taskCount === 'number'
			? {
					label: $i18n.t('Tasks'),
					value: panelContextSummary.taskCount
				}
			: null
	].filter(Boolean);
	$: workspaceHeaderStats = [
		typeof panelContextSummary.workspaceVisibleCount === 'number'
			? {
					label: $i18n.t('Workspace'),
					value: panelContextSummary.workspaceVisibleCount
				}
			: null,
		typeof panelContextSummary.chatAttachedFileCount === 'number'
			? {
					label: $i18n.t('Attached'),
					value: panelContextSummary.chatAttachedFileCount
				}
			: null,
		typeof panelContextSummary.generatedFileCount === 'number'
			? {
					label: $i18n.t('Generated'),
					value: panelContextSummary.generatedFileCount
				}
			: null
	].filter(Boolean);

	const getOperatorFallbackTab = (): PanelTabId => {
		if (showSessionTab) return 'session';
		if (showSessionTab) return 'history';
		if (showFilesTab) return 'files';
		if (showTasksTab) return 'tasks';
		if (showProfileTab) return 'profile';
		if (showSkillsTab) return 'skills';
		if (showMemoryTab) return 'memory';
		if (showOverviewTab) return 'overview';
		if (showTodosTab) return 'todos';
		if (showAdvancedTab) return 'controls';
		return 'files';
	};

	const toggleInspectTabs = () => {
		if (activeTabInInspectGroup && inspectTabsExpanded) {
			activeTab = getOperatorFallbackTab();
			inspectTabsExpanded = false;
			return;
		}

		inspectTabsExpanded = !inspectTabsExpanded;
	};

	const handleWorkspaceStatusChange = (nextStatus: WorkspacePanelStatus) => {
		workspaceStatus = nextStatus;
	};

	const handleHermesProfileSwitched = async (payload: Record<string, any> | null = null) => {
		hermesRuntimeStore.set(null);
		hermesWorkspacesStore.set(null);
		hermesProfilesStore.set(null);
		hermesContextLoaded.set(false);
		hermesProfilesLoaded.set(false);
		workspaceStatus = null;

		await onHermesProfileSwitched(payload);

		if ($showControls) {
			await ensureHermesContextBundle(localStorage?.token, {
				force: true,
				includeProfiles: true
			});
		}
	};

	const handleHermesWorkspaceSwitched = (payload: HermesWorkspacesResponse) => {
		hermesWorkspacesStore.set(payload);
		hermesContextLoaded.set(true);
		workspaceStatus = null;
	};

	// Tab fallback: if active tab becomes hidden, switch to next available
	$: if (!showOverviewTab && activeTab === 'overview') activeTab = getOperatorFallbackTab();
	$: if (!showSessionTab && activeTab === 'session') activeTab = getOperatorFallbackTab();
	$: if (!showSessionTab && activeTab === 'history') activeTab = getOperatorFallbackTab();
	$: if (!showFilesTab && activeTab === 'files') activeTab = getOperatorFallbackTab();
	$: if (!showSkillsTab && activeTab === 'skills') activeTab = getOperatorFallbackTab();
	$: if (!showMemoryTab && activeTab === 'memory') activeTab = getOperatorFallbackTab();
	$: if (!showTasksTab && activeTab === 'tasks') activeTab = getOperatorFallbackTab();
	$: if (!showTodosTab && activeTab === 'todos') activeTab = getOperatorFallbackTab();
	$: if (!showAdvancedTab && activeTab === 'controls') activeTab = getOperatorFallbackTab();

	// Auto-close if there are no visible tabs
	$: if (
		!showAdvancedTab &&
		!showFilesTab &&
		!showOverviewTab &&
		!showSessionTab &&
		!showProfileTab &&
		!showSkillsTab &&
		!showMemoryTab &&
		!showTasksTab &&
		!showTodosTab
	) {
		showControls.set(false);
	}

	$: if ($chatControlsOpenTarget) {
		const requestedTab: PanelTabId =
			$chatControlsOpenTarget === 'workspace'
				? 'files'
				: $chatControlsOpenTarget === 'session'
					? 'history'
					: 'tasks';

		if (
			(requestedTab === 'files' && showFilesTab) ||
			(requestedTab === 'history' && showSessionTab) ||
			(requestedTab === 'tasks' && showTasksTab)
		) {
			activeTab = requestedTab;
		}

		chatControlsOpenTarget.set(null);
	}

	// Auto-switch to Workspace tab when display_file is triggered
	$: if ($showFileNavPath) {
		activeTab = 'files';
		showControls.set(true);
	}

	$: if ($showControls && (!$hermesContextLoaded || !$hermesProfilesLoaded)) {
		if (!$hermesContextLoading && !$hermesProfilesLoading) {
			void ensureHermesContextBundle(localStorage?.token, { includeProfiles: true });
		}
	}

	// Auto-open Workspace tab when a terminal is selected (suppress panel open when full-screen)
	$: if ($selectedTerminalId) {
		activeTab = 'files';
		if (largeScreen) {
			showControls.set(true);
		}
	}

	// Attach a terminal file to the chat input
	const handleTerminalAttach = async (blob: Blob, name: string, contentType: string) => {
		const tempItemId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: '',
			name,
			collection_name: '',
			status: 'uploading',
			error: '',
			itemId: tempItemId,
			size: blob.size
		};

		files = [...files, fileItem];

		try {
			const file = new File([blob], name, { type: contentType || 'application/octet-stream' });
			const uploaded = await uploadFile(localStorage.token, file);
			if (!uploaded) throw new Error('Upload failed');

			const idx = files.findIndex((f) => f.itemId === tempItemId);
			if (idx !== -1) {
				files[idx] = {
					...fileItem,
					status: 'uploaded',
					file: uploaded,
					id: uploaded.id,
					url: `${uploaded.id}`,
					collection_name: uploaded?.meta?.collection_name
				};
				files = files;
			}
			toast.success($i18n.t('File attached to chat'));
		} catch (e) {
			files = files.filter((f) => f.itemId !== tempItemId);
			toast.error($i18n.t('Failed to attach file'));
		}
	};

	export const openPane = () => {
		if (!pane) {
			return;
		}

		if (parseInt(localStorage?.chatControlsSize)) {
			const container = document.getElementById('chat-container');
			if (!container?.clientWidth) {
				return;
			}
			let size = Math.floor(
				(parseInt(localStorage?.chatControlsSize) / container.clientWidth) * 100
			);
			pane.resize(size);
		} else {
			pane.resize(minSize);
		}
	};

	const handleMediaQuery = async (e: MediaQueryList | MediaQueryListEvent) => {
		if (e.matches) {
			largeScreen = true;
			if ($showCallOverlay) {
				showCallOverlay.set(false);
				await tick();
				showCallOverlay.set(true);
			}
		} else {
			largeScreen = false;
			if ($showCallOverlay) {
				showCallOverlay.set(false);
				await tick();
				showCallOverlay.set(true);
			}
			pane = undefined;
		}
	};

	const onMouseDown = () => {
		dragged = true;
	};
	const onMouseUp = () => {
		dragged = false;
	};

	onMount(() => {
		const mediaQuery = window.matchMedia('(min-width: 1024px)');
		mediaQuery.addEventListener('change', handleMediaQuery);
		handleMediaQuery(mediaQuery);

		let resizeObserver: ResizeObserver | null = null;
		let isDestroyed = false;

		// Wait for Svelte to render the Pane after largeScreen changed
		const init = async () => {
			await tick();

			if (isDestroyed) return;

			// If controls were persisted as open, set the pane to the saved size
			if ($showControls && pane) {
				openPane();
			}

			setTimeout(() => {
				paneReady = true;
			}, 0);

			const container = document.getElementById('chat-container') as HTMLElement;
			if (!container) return;

			minSize = Math.floor((350 / container.clientWidth) * 100);
			resizeObserver = new ResizeObserver((entries) => {
				for (let entry of entries) {
					const width = entry.contentRect.width;
					minSize = Math.floor((350 / width) * 100);
					if ($showControls) {
						if (pane && pane.isExpanded() && pane.getSize() < minSize) {
							pane.resize(minSize);
						} else {
							let size = Math.floor(
								(parseInt(localStorage?.chatControlsSize) / container.clientWidth) * 100
							);
							if (size < minSize && pane) pane.resize(minSize);
						}
					}
				}
			});
			resizeObserver.observe(container);
		};
		init();

		document.addEventListener('mousedown', onMouseDown);
		document.addEventListener('mouseup', onMouseUp);

		return () => {
			isDestroyed = true;
			paneReady = false;
			resizeObserver?.disconnect();
			if (!largeScreen) {
				showControls.set(false);
			}
			mediaQuery.removeEventListener('change', handleMediaQuery);
			document.removeEventListener('mousedown', onMouseDown);
			document.removeEventListener('mouseup', onMouseUp);
		};
	});

	const closeHandler = () => {
		if (!largeScreen) {
			showControls.set(false);
		}
		showArtifacts.set(false);
		showEmbeds.set(false);
		if ($showCallOverlay) showCallOverlay.set(false);
	};

	$: if (
		paneReady &&
		!chatId &&
		activeTab !== 'session' &&
		activeTab !== 'history' &&
		$chatControlsOpenTarget !== 'session'
	) {
		closeHandler();
	}

	// Helper: is a "special" full-screen panel active?
	$: specialPanel = $showCallOverlay || $showArtifacts || $showEmbeds;
</script>

{#if !largeScreen}
	{#if $showControls}
		<Drawer
			show={$showControls}
			onClose={() => showControls.set(false)}
			className="min-h-[100dvh] !bg-white dark:!bg-gray-850"
		>
			<div class="h-[100dvh] flex flex-col">
				{#if $showCallOverlay}
					<div
						class="h-full max-h-[100dvh] bg-white text-gray-700 dark:bg-black dark:text-gray-300 flex justify-center"
					>
						<CallOverlay
							bind:files
							{submitPrompt}
							{stopResponse}
							{modelId}
							{chatId}
							{eventTarget}
							on:close={() => showControls.set(false)}
						/>
					</div>
					{:else if $showEmbeds}
						<Embeds />
					{:else if $showArtifacts}
						<Artifacts />
				{:else}
					<!-- Controls + Workspace tabs -->
							<div class="flex flex-col h-full min-h-0">
								<!-- Tab bar -->
								<div class="flex items-center justify-between px-2 pt-2 pb-2 shrink-0">
									<div class="flex gap-1 min-w-0 overflow-x-auto scrollbar-hidden">
										{#each primaryTabs as tab}
											<button
												class="px-2.5 py-1 text-sm rounded-lg transition whitespace-nowrap {activeTab ===
												tab.id
													? 'bg-gray-100 dark:bg-gray-800 font-medium text-gray-900 dark:text-white'
													: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
												on:click={() => (activeTab = tab.id)}
											>
												{tab.label}
											</button>
										{/each}
										{#if inspectTabs.length > 0}
											<button
												class="px-2.5 py-1 text-sm rounded-lg transition whitespace-nowrap {(inspectTabsExpanded ||
												activeTabInInspectGroup)
													? 'bg-gray-100 dark:bg-gray-800 font-medium text-gray-900 dark:text-white'
													: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
												on:click={toggleInspectTabs}
											>
												{$i18n.t('Inspect')}
											</button>
										{/if}
									</div>
									<button
								class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
								on:click={() => showControls.set(false)}
								aria-label={$i18n.t('Close')}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.5"
									class="size-4"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
										</svg>
									</button>
								</div>
								{#if inspectTabsExpanded && inspectTabs.length > 0}
									<div
										class="flex gap-1 overflow-x-auto border-b border-gray-100 px-2 pb-2 dark:border-gray-800"
									>
										{#each inspectTabs as tab}
											<button
												class="px-2.5 py-1 text-[11px] rounded-full transition whitespace-nowrap {activeTab ===
												tab.id
													? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
													: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
												on:click={() => (activeTab = tab.id)}
											>
												{tab.label}
											</button>
										{/each}
									</div>
								{/if}

							<div
							class="flex-1 min-h-0 {activeTab === 'overview'
								? 'h-full'
								: activeTab === 'controls'
									? 'overflow-y-auto px-3 pt-1'
									: ''}"
						>
							{#if showPrimaryContextSummary}
								<div class="px-3 pt-3 pb-2">
								<div
									class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-3 dark:border-gray-800/80 dark:bg-gray-900/50"
								>
									<div class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
											{$i18n.t('Current context')}
									</div>

										<div class="mt-2">
											<HermesContextBar
												summary={panelContextSummary}
												compact={true}
												on:workspace={() => (activeTab = 'files')}
												on:session={() => (activeTab = 'session')}
												on:profile={() => {
													inspectTabsExpanded = true;
													activeTab = 'profile';
												}}
											/>
										</div>

										{#if panelStats.length > 0}
											<div class="mt-3 grid grid-cols-2 gap-2">
												{#each panelStats as stat}
													<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
														<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
															{stat.label}
														</div>
														<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
															{stat.value}
														</div>
													</div>
												{/each}
											</div>
										{/if}
									</div>
								</div>
							{:else if showInspectContextSummary}
								<div class="px-3 pt-3 pb-1">
									<div class="rounded-xl bg-gray-50/80 px-3 py-2 dark:bg-gray-900/40">
										<div class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
											{$i18n.t('Inspect')}
										</div>
										<div class="mt-2">
											<HermesContextBar
												summary={panelContextSummary}
												compact={true}
												on:workspace={() => (activeTab = 'files')}
												on:session={() => (activeTab = 'session')}
												on:profile={() => (activeTab = 'profile')}
											/>
										</div>
									</div>
								</div>
							{/if}

							{#if activeTab === 'overview'}
								<Overview
									{history}
									onNodeClick={(e: any) => {
										const node = e.node;
										showMessage(node.data.message, true);
									}}
									onClose={() => showControls.set(false)}
								/>
							{:else if activeTab === 'profile'}
								<HermesProfilePanel
									active={activeTab === 'profile'}
									{taskIds}
									{hermesStreamActive}
									onProfileSwitched={handleHermesProfileSwitched}
								/>
							{:else if activeTab === 'skills'}
								<HermesSkillsPanel active={activeTab === 'skills'} />
							{:else if activeTab === 'memory'}
								<HermesMemoryPanel active={activeTab === 'memory'} />
							{:else if activeTab === 'tasks'}
								<HermesTasksPanel active={activeTab === 'tasks'} {taskIds} {stopResponse} />
							{:else if activeTab === 'todos'}
								<HermesTodosPanel active={activeTab === 'todos'} {history} />
							{:else if activeTab === 'session'}
								<HermesSessionPanel
									active={activeTab === 'session'}
									{chatId}
									{chatHermesSession}
									{chatMeta}
									{history}
									{models}
									{taskIds}
									{chatFiles}
									mode="context"
								/>
							{:else if activeTab === 'history'}
								<HermesSessionPanel
									active={activeTab === 'history'}
									{chatId}
									{chatHermesSession}
									{chatMeta}
									{history}
									{models}
									{taskIds}
									{chatFiles}
									mode="history"
								/>
							{:else if activeTab === 'files' && $selectedTerminalId}
								<div class="flex h-full min-h-0 flex-col">
									<HermesWorkspaceHeader
										title={workspaceTitle}
										subtitle={workspaceSubtitle}
										badge={workspaceBadge}
										metaItems={workspaceMetaItems}
										stats={workspaceHeaderStats}
									/>
									<div class="flex-1 min-h-0">
										<FileNav
											onAttach={handleTerminalAttach}
											onWorkspaceStatusChange={handleWorkspaceStatusChange}
										/>
									</div>
								</div>
							{:else if activeTab === 'files' && codeInterpreterEnabled}
								<div class="flex h-full min-h-0 flex-col">
									<HermesWorkspaceHeader
										title={workspaceTitle}
										subtitle={workspaceSubtitle}
										badge={workspaceBadge}
										metaItems={workspaceMetaItems}
										stats={workspaceHeaderStats}
									/>
									<div class="flex-1 min-h-0">
										<PyodideFileNav
											onAttach={handleTerminalAttach}
											onWorkspaceStatusChange={handleWorkspaceStatusChange}
										/>
									</div>
								</div>
							{:else if activeTab === 'files'}
								<HermesWorkspaceStub
									active={activeTab === 'files'}
									{chatId}
									{chatFiles}
									generatedFiles={generatedWorkspaceFiles}
									{taskIds}
									hermesWorkspaces={$hermesWorkspacesStore?.items ?? []}
									onAttach={handleTerminalAttach}
									onHermesWorkspaceSwitched={handleHermesWorkspaceSwitched}
									onWorkspaceStatusChange={handleWorkspaceStatusChange}
								/>
							{:else}
								<Controls embed={true} {models} bind:chatFiles bind:params />
							{/if}
						</div>
					</div>
				{/if}
			</div>
		</Drawer>
	{/if}
{:else}
	{#if $showControls}
		<PaneResizer
			class="relative flex items-center justify-center group border-l border-gray-50 dark:border-gray-850/30 hover:border-gray-200 dark:hover:border-gray-800 transition z-20"
			id="controls-resizer"
		>
			<div
				class="absolute -left-1.5 -right-1.5 -top-0 -bottom-0 z-20 cursor-col-resize bg-transparent"
			></div>
		</PaneResizer>
	{/if}

	<Pane
		bind:pane
			defaultSize={0}
			onResize={(size) => {
				if ($showControls && pane?.isExpanded()) {
					if (size < minSize) pane.resize(minSize);
					if (size < minSize) {
						localStorage.chatControlsSize = 0;
					} else {
						const container = document.getElementById('chat-container');
						if (container?.clientWidth) {
							localStorage.chatControlsSize = Math.floor((size / 100) * container.clientWidth);
						}
					}
				}
			}}
		onCollapse={() => {
			if (paneReady) showControls.set(false);
		}}
		collapsible={true}
		class="z-10 bg-white dark:bg-gray-850"
	>
		{#if $showControls}
			<div class="flex max-h-full min-h-full">
				<div
					class="w-full {specialPanel && !$showCallOverlay
						? ' '
						: 'bg-white dark:shadow-lg dark:bg-gray-850'} z-40 pointer-events-auto {activeTab ===
					'files'
						? ''
						: 'overflow-y-auto'} scrollbar-hidden"
					id="controls-container"
				>
					{#if $showCallOverlay}
						<div class="w-full h-full flex justify-center">
							<CallOverlay
								bind:files
								{submitPrompt}
								{stopResponse}
								{modelId}
								{chatId}
								{eventTarget}
								on:close={() => showControls.set(false)}
							/>
						</div>
						{:else if $showEmbeds}
							<Embeds overlay={dragged} />
						{:else if $showArtifacts}
							<Artifacts overlay={dragged} />
					{:else}
						<!-- Controls + Workspace tabs -->
						<div class="flex flex-col h-full min-h-0">
							<!-- Tab bar -->
							<div class="flex items-center justify-between px-2 pt-2 pb-2 shrink-0">
								<div class="flex gap-1 min-w-0 overflow-x-auto scrollbar-hidden">
									{#each primaryTabs as tab}
										<button
											class="px-2.5 py-1 text-sm rounded-lg transition whitespace-nowrap {activeTab ===
											tab.id
												? 'bg-gray-100 dark:bg-gray-800 font-medium text-gray-900 dark:text-white'
												: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
											on:click={() => (activeTab = tab.id)}
										>
											{tab.label}
										</button>
									{/each}
									{#if inspectTabs.length > 0}
										<button
											class="px-2.5 py-1 text-sm rounded-lg transition whitespace-nowrap {(inspectTabsExpanded ||
											activeTabInInspectGroup)
												? 'bg-gray-100 dark:bg-gray-800 font-medium text-gray-900 dark:text-white'
												: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}"
											on:click={toggleInspectTabs}
										>
											{$i18n.t('Inspect')}
										</button>
									{/if}
								</div>
								<button
									class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
									on:click={() => showControls.set(false)}
									aria-label={$i18n.t('Close')}
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.5"
										class="size-4"
									>
										<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
									</svg>
								</button>
							</div>
							{#if inspectTabsExpanded && inspectTabs.length > 0}
								<div
									class="flex gap-1 overflow-x-auto border-b border-gray-100 px-2 pb-2 dark:border-gray-800"
								>
									{#each inspectTabs as tab}
										<button
											class="px-2.5 py-1 text-[11px] rounded-full transition whitespace-nowrap {activeTab ===
											tab.id
												? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
												: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
											on:click={() => (activeTab = tab.id)}
										>
											{tab.label}
										</button>
									{/each}
								</div>
							{/if}

							<div
								class="flex-1 min-h-0 {activeTab === 'overview'
									? 'h-full'
									: activeTab === 'controls'
										? 'overflow-y-auto px-3 pt-1'
										: ''}"
							>
								{#if showPrimaryContextSummary}
									<div class="px-3 pt-3 pb-2">
										<div
											class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-3 dark:border-gray-800/80 dark:bg-gray-900/50"
										>
											<div class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
												{$i18n.t('Current context')}
											</div>

											<div class="mt-2">
												<HermesContextBar
													summary={panelContextSummary}
													compact={true}
													on:workspace={() => (activeTab = 'files')}
													on:session={() => (activeTab = 'session')}
													on:profile={() => {
														inspectTabsExpanded = true;
														activeTab = 'profile';
													}}
												/>
											</div>

											{#if panelStats.length > 0}
												<div class="mt-3 grid grid-cols-2 gap-2">
													{#each panelStats as stat}
														<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
															<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
																{stat.label}
															</div>
															<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
																{stat.value}
															</div>
														</div>
													{/each}
												</div>
											{/if}
										</div>
									</div>
								{:else if showInspectContextSummary}
									<div class="px-3 pt-3 pb-1">
										<div class="rounded-xl bg-gray-50/80 px-3 py-2 dark:bg-gray-900/40">
											<div class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
												{$i18n.t('Inspect')}
											</div>
											<div class="mt-2">
												<HermesContextBar
													summary={panelContextSummary}
													compact={true}
													on:workspace={() => (activeTab = 'files')}
													on:session={() => (activeTab = 'session')}
													on:profile={() => (activeTab = 'profile')}
												/>
											</div>
										</div>
									</div>
								{/if}

								{#if activeTab === 'overview'}
									<Overview
										{history}
										onNodeClick={(e: any) => {
											const node = e.node;
											if (node?.data?.message?.favorite) {
												history.messages[node.data.message.id].favorite = true;
											} else {
												history.messages[node.data.message.id].favorite = null;
											}
											showMessage(node.data.message, true);
										}}
										onClose={() => showControls.set(false)}
									/>
								{:else if activeTab === 'session'}
									<HermesSessionPanel
										active={activeTab === 'session'}
										{chatId}
										{chatHermesSession}
										{chatMeta}
										{history}
										{models}
										{taskIds}
										{chatFiles}
										mode="context"
									/>
								{:else if activeTab === 'history'}
									<HermesSessionPanel
										active={activeTab === 'history'}
										{chatId}
										{chatHermesSession}
										{chatMeta}
										{history}
										{models}
										{taskIds}
										{chatFiles}
										mode="history"
									/>
								{:else if activeTab === 'profile'}
									<HermesProfilePanel
										active={activeTab === 'profile'}
										{taskIds}
										{hermesStreamActive}
										onProfileSwitched={handleHermesProfileSwitched}
									/>
								{:else if activeTab === 'skills'}
									<HermesSkillsPanel active={activeTab === 'skills'} />
								{:else if activeTab === 'memory'}
									<HermesMemoryPanel active={activeTab === 'memory'} />
								{:else if activeTab === 'tasks'}
									<HermesTasksPanel active={activeTab === 'tasks'} {taskIds} {stopResponse} />
								{:else if activeTab === 'todos'}
									<HermesTodosPanel active={activeTab === 'todos'} {history} />
								{:else if activeTab === 'files' && $selectedTerminalId}
									<div class="flex h-full min-h-0 flex-col">
										<HermesWorkspaceHeader
											title={workspaceTitle}
											subtitle={workspaceSubtitle}
											badge={workspaceBadge}
											metaItems={workspaceMetaItems}
											stats={workspaceHeaderStats}
										/>
										<div class="flex-1 min-h-0">
											<FileNav
												onAttach={handleTerminalAttach}
												onWorkspaceStatusChange={handleWorkspaceStatusChange}
												overlay={dragged}
											/>
										</div>
									</div>
								{:else if activeTab === 'files' && codeInterpreterEnabled}
									<div class="flex h-full min-h-0 flex-col">
										<HermesWorkspaceHeader
											title={workspaceTitle}
											subtitle={workspaceSubtitle}
											badge={workspaceBadge}
											metaItems={workspaceMetaItems}
											stats={workspaceHeaderStats}
										/>
										<div class="flex-1 min-h-0">
											<PyodideFileNav
												onAttach={handleTerminalAttach}
												onWorkspaceStatusChange={handleWorkspaceStatusChange}
												overlay={dragged}
											/>
										</div>
									</div>
								{:else if activeTab === 'files'}
									<HermesWorkspaceStub
										active={activeTab === 'files'}
										{chatId}
										{chatFiles}
										generatedFiles={generatedWorkspaceFiles}
										{taskIds}
										hermesWorkspaces={$hermesWorkspacesStore?.items ?? []}
										onAttach={handleTerminalAttach}
										onHermesWorkspaceSwitched={handleHermesWorkspaceSwitched}
										onWorkspaceStatusChange={handleWorkspaceStatusChange}
									/>
								{:else}
									<Controls embed={true} {models} bind:chatFiles bind:params />
								{/if}
							</div>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</Pane>
{/if}
