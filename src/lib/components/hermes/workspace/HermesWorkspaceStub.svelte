<script context="module" lang="ts">
	let savedSelectionByChatKey: Record<string, string | null> = {};

	type HermesWorkspaceContinuityState = {
		rootPath: string | null;
		browsePath: string | null;
		previewReference: string | null;
		lastFocusedReference: string | null;
	};

	const createWorkspaceContinuityState = (): HermesWorkspaceContinuityState => ({
		rootPath: null,
		browsePath: null,
		previewReference: null,
		lastFocusedReference: null
	});

	let savedWorkspaceStateByChatKey: Record<string, HermesWorkspaceContinuityState> = {};
</script>

<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		getHermesWorkspaceBrowse,
		getHermesWorkspaceFileUrl,
		type HermesWorkspaceBrowseEntry,
		switchHermesWorkspace,
		type HermesWorkspace,
		type HermesWorkspaceSwitchResponse
	} from '$lib/apis/hermes';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { getFileById, getFileContentById } from '$lib/apis/files';
	import type { WorkspacePanelStatus } from '$lib/stores';
	import { copyToClipboard, formatFileSize } from '$lib/utils';
	import HermesWorkspaceTree from './HermesWorkspaceTree.svelte';
	import {
		buildHermesWorkspaceSurfaceItems,
		buildHermesLinkedWorkspaceSummary,
		getHermesWorkspaceSurfaceItemLabel,
		getHermesWorkspacePreviewMode,
		type HermesGeneratedWorkspaceFile,
		type HermesWorkspaceSurfaceItem
	} from '$lib/utils/hermesWorkspace';
	import {
		buildHermesWorkspaceTree,
		normalizeHermesWorkspaceTreePath,
		type HermesWorkspaceTreeEntry
	} from '$lib/utils/hermesWorkspaceTree';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import FilePreview from '$lib/components/chat/FileNav/FilePreview.svelte';
	import HermesWorkspaceGuideRow from './HermesWorkspaceGuideRow.svelte';

	type TranslationStore = {
		subscribe: (
			run: (value: { t: (key: string, params?: Record<string, unknown>) => string }) => void
		) => () => void;
	};

	const i18n = getContext<TranslationStore>('i18n');

	export let active = false;
	export let chatId: string | null = null;
	export let chatFiles: Array<Record<string, unknown>> = [];
	export let generatedFiles: HermesGeneratedWorkspaceFile[] = [];
	export let taskIds: string[] | null = null;
	export let hermesWorkspaces: HermesWorkspace[] = [];
	export let onAttach:
		| ((blob: Blob, name: string, contentType: string) => Promise<void> | void)
		| null = null;
	export let onHermesWorkspaceSwitched: (payload: HermesWorkspaceSwitchResponse) => void = () => {};
	export let onWorkspaceStatusChange: ((status: WorkspacePanelStatus) => void) | null = null;

	let selectedItemId: string | null = null;
	let hydratedChatKey: string | null = null;
	let loadedItemId: string | null = null;
	let loadRequestId = 0;
	let selectedItem: HermesWorkspaceSurfaceItem | null = null;
	let selectedWorkspaceItem: HermesWorkspaceSurfaceItem | null = null;
	let switchingWorkspacePath: string | null = null;
	let workspaceBrowseLoaded = false;
	let workspaceBrowseLoading = false;
	let workspaceBrowseError = '';
	let workspaceBrowsePath = '';
	let workspaceBrowseRootPath = '';
	let workspaceBrowseEntries: HermesWorkspaceBrowseEntry[] = [];
	let workspaceTreeEntriesByPath: Record<string, HermesWorkspaceBrowseEntry[]> = {};
	let workspaceTreeEntries: HermesWorkspaceTreeEntry[] = [];
	let workspaceTreeExpandedPaths: string[] = [];
	let workspaceTreeLoadingPaths: string[] = [];
	let workspaceContinuityState = createWorkspaceContinuityState();

	let selectedItemLoading = false;
	let previewError = '';
	let previewUnsupported = false;

	let fileContent: string | null = null;
	let fileImageUrl: string | null = null;
	let fileVideoUrl: string | null = null;
	let fileAudioUrl: string | null = null;
	let filePdfData: ArrayBuffer | null = null;
	let fileSqliteData: ArrayBuffer | null = null;
	let fileOfficeHtml: string | null = null;
	let fileOfficeSlides: string[] | null = null;
	let currentSlide = 0;
	let excelSheetNames: string[] = [];
	let selectedExcelSheet = '';
	let excelWorkbook: import('xlsx').WorkBook | null = null;

	$: workspaceItems = buildHermesWorkspaceSurfaceItems(chatFiles, generatedFiles);
	$: linkedWorkspaceSummary = buildHermesLinkedWorkspaceSummary(chatFiles, generatedFiles);
	$: availableHermesWorkspaces = (Array.isArray(hermesWorkspaces) ? hermesWorkspaces : []).filter(
		(workspace): workspace is HermesWorkspace =>
			!!workspace && typeof workspace.path === 'string' && !!workspace.path
	);
	$: activeHermesWorkspace =
		availableHermesWorkspaces.find((workspace) => workspace.is_active) ??
		availableHermesWorkspaces[0] ??
		null;
	$: generatedWorkspaceItems = workspaceItems.filter((item) => item.source === 'generated');
	$: chatWorkspaceItems = workspaceItems.filter((item) => item.source === 'chat');
	$: latestGeneratedWorkspaceItem = generatedWorkspaceItems[0] ?? null;
	$: latestChatWorkspaceItem = chatWorkspaceItems[0] ?? null;
	$: activeChatKey = chatId ?? '__current_chat__';
	$: selectedChatItem = workspaceItems.find((item) => item.id === selectedItemId) ?? null;
	$: selectedItem = selectedWorkspaceItem ?? selectedChatItem ?? null;
	$: hasActiveTasks = (taskIds?.length ?? 0) > 0;
	$: workspaceBrowserEntries = (
		workspaceTreeEntriesByPath[currentWorkspacePath] ?? workspaceBrowseEntries ?? []
	)
		.filter((entry) => !!entry?.name)
		.sort((left, right) => {
			if (left.type !== right.type) {
				return left.type === 'directory' ? -1 : 1;
			}

			return left.name.localeCompare(right.name);
		});
	$: currentWorkspacePath = workspaceBrowsePath || activeHermesWorkspace?.path || '';
	$: canBrowseWorkspace = !!activeHermesWorkspace?.path;
	$: workspaceTreeEntries = Object.entries(workspaceTreeEntriesByPath).flatMap(
		([basePath, entries]) =>
			(entries ?? []).map((entry) => ({
				path: joinWorkspacePath(basePath, entry.name),
				name: entry.name,
				type: entry.type,
				size: entry.size ?? null,
				modified: entry.modified ?? null
			}))
	);
	$: workspaceTreeNodes =
		workspaceBrowseRootPath && workspaceTreeEntries.length > 0
			? buildHermesWorkspaceTree(workspaceTreeEntries, workspaceBrowseRootPath)
			: [];
	$: visibleWorkspaceTreeCount = countWorkspaceTreeNodes(workspaceTreeNodes);
	$: selectedWorkspaceTreePath =
		selectedWorkspaceItem?.source === 'workspace' ? selectedWorkspaceItem.reference : null;
	$: rememberedWorkspaceTreePath = selectedWorkspaceItem
		? null
		: workspaceContinuityState.lastFocusedReference;
	$: hasWorkspaceParent =
		!!workspaceBrowsePath &&
		!!workspaceBrowseRootPath &&
		normalizeWorkspacePath(workspaceBrowsePath) !== normalizeWorkspacePath(workspaceBrowseRootPath);
	$: workspacePathTrail =
		currentWorkspacePath && workspaceBrowseRootPath
			? buildWorkspacePathTrail(
					currentWorkspacePath,
					workspaceBrowseRootPath,
					activeHermesWorkspace?.name || getWorkspaceLeafName(workspaceBrowseRootPath)
				)
			: [];
	$: workspaceBrowserMeta = [
		$i18n.t('Workspace path: {{PATH}}', { PATH: currentWorkspacePath }),
		$i18n.t('Tree entries: {{COUNT}}', { COUNT: visibleWorkspaceTreeCount }),
		$i18n.t('Linked items: {{COUNT}}', { COUNT: linkedWorkspaceSummary.totalLinked })
	].filter(Boolean);
	$: generatedWorkspaceMeta = [
		$i18n.t('Linked items: {{COUNT}}', { COUNT: linkedWorkspaceSummary.totalLinked }),
		$i18n.t('Generated: {{COUNT}}', { COUNT: linkedWorkspaceSummary.generated }),
		latestGeneratedWorkspaceItem?.executionName
			? $i18n.t('Latest run: {{NAME}}', { NAME: latestGeneratedWorkspaceItem.executionName })
			: ''
	].filter(Boolean);
	$: chatWorkspaceMeta = [
		$i18n.t('Linked items: {{COUNT}}', { COUNT: linkedWorkspaceSummary.totalLinked }),
		$i18n.t('Attached: {{COUNT}}', { COUNT: linkedWorkspaceSummary.attached })
	].filter(Boolean);
	$: selectedItemMetaItems = selectedItem
		? [
				getHermesWorkspaceSurfaceItemLabel(selectedItem),
				selectedItem.executionName
					? $i18n.t('Run: {{NAME}}', { NAME: selectedItem.executionName })
					: '',
				selectedItem.type !== 'file' ? $i18n.t('Type: {{TYPE}}', { TYPE: selectedItem.type }) : '',
				selectedItem.size ? formatFileSize(selectedItem.size) : '',
				selectedItem.reference && selectedItem.reference !== selectedItem.name
					? selectedItem.reference
					: ''
			].filter(Boolean)
		: [];
	$: canAttachSelectedItem =
		!!onAttach &&
		!!selectedItem &&
		(!!selectedItem.fileId ||
			!!selectedItem.url ||
			(typeof selectedItem.content === 'string' && selectedItem.content.length >= 0));
	$: canOpenSelectedItem =
		!!selectedItem &&
		(!!selectedItem.url ||
			!!selectedItem.fileId ||
			(typeof selectedItem.content === 'string' && selectedItem.content.length > 0));

	$: if (activeChatKey !== hydratedChatKey) {
		hydratedChatKey = activeChatKey;
		workspaceContinuityState =
			savedWorkspaceStateByChatKey[activeChatKey] ?? createWorkspaceContinuityState();
		selectedItemId = savedSelectionByChatKey[activeChatKey] ?? null;
		selectedWorkspaceItem = workspaceContinuityState.previewReference
			? createWorkspaceSurfaceItem(workspaceContinuityState.previewReference)
			: null;
		workspaceBrowseLoaded = false;
		workspaceBrowseLoading = false;
			workspaceBrowseError = '';
			workspaceBrowsePath = '';
			workspaceBrowseRootPath = '';
			workspaceBrowseEntries = [];
			workspaceTreeEntriesByPath = {};
			workspaceTreeExpandedPaths = [];
			workspaceTreeLoadingPaths = [];
			loadedItemId = null;
			clearPreviewState();
		}

	$: if (selectedItemId && !workspaceItems.some((item) => item.id === selectedItemId)) {
		selectedItemId = null;
		loadedItemId = null;
		savedSelectionByChatKey[activeChatKey] = null;
		clearPreviewState();
	}

	$: if (activeHermesWorkspace?.path !== workspaceBrowseRootPath) {
		const nextRootPath = activeHermesWorkspace?.path ?? '';
		const canRestoreWorkspaceState =
			!!nextRootPath && workspaceContinuityState.rootPath === nextRootPath;

		workspaceBrowseLoaded = false;
		workspaceBrowseLoading = false;
			workspaceBrowseError = '';
			workspaceBrowsePath = canRestoreWorkspaceState
				? (workspaceContinuityState.browsePath ?? '')
				: '';
			workspaceBrowseRootPath = nextRootPath;
			workspaceBrowseEntries = [];
			workspaceTreeEntriesByPath = {};
			workspaceTreeExpandedPaths = nextRootPath ? [normalizeWorkspacePath(nextRootPath)] : [];
			workspaceTreeLoadingPaths = [];
			selectedWorkspaceItem =
				canRestoreWorkspaceState && workspaceContinuityState.previewReference
					? createWorkspaceSurfaceItem(workspaceContinuityState.previewReference)
				: null;

		if (!canRestoreWorkspaceState) {
			persistWorkspaceContinuityState({
				rootPath: nextRootPath || null,
				browsePath: null,
				previewReference: null,
				lastFocusedReference: null
			});
		}
	}

	$: if (selectedItem?.id !== loadedItemId) {
		loadedItemId = selectedItem?.id ?? null;
		if (selectedItem) {
			void loadSelectedItem(selectedItem);
		} else {
			clearPreviewState();
		}
	}

	$: if (active && canBrowseWorkspace && !workspaceBrowseLoaded && !workspaceBrowseLoading) {
		void hydrateWorkspaceTree(workspaceBrowsePath || activeHermesWorkspace?.path || null);
	}

	$: if (active) {
		const visibleItemCount = selectedItem
			? 0
			: canBrowseWorkspace
				? visibleWorkspaceTreeCount
				: linkedWorkspaceSummary.totalLinked;
		onWorkspaceStatusChange?.({
			source: 'stub',
			currentPath: currentWorkspacePath || undefined,
			itemCount: canBrowseWorkspace ? visibleWorkspaceTreeCount : workspaceItems.length,
			visibleItemCount,
			linkedItemCount: linkedWorkspaceSummary.totalLinked,
			selectedFile: selectedItem?.reference ?? null,
			selectedFileName: selectedItem?.name ?? null,
			attachEnabled: canAttachSelectedItem
		});
	}

	const clearPreviewState = () => {
		if (fileImageUrl) {
			URL.revokeObjectURL(fileImageUrl);
		}
		if (fileVideoUrl) {
			URL.revokeObjectURL(fileVideoUrl);
		}
		if (fileAudioUrl) {
			URL.revokeObjectURL(fileAudioUrl);
		}

		fileContent = null;
		fileImageUrl = null;
		fileVideoUrl = null;
		fileAudioUrl = null;
		filePdfData = null;
		fileSqliteData = null;
		fileOfficeHtml = null;
		fileOfficeSlides = null;
		currentSlide = 0;
		excelSheetNames = [];
		selectedExcelSheet = '';
		excelWorkbook = null;
		previewError = '';
		previewUnsupported = false;
	};

	const getErrorMessage = (error: unknown, fallback: string) => {
		if (typeof error === 'string') {
			return error;
		}

		if (error && typeof error === 'object') {
			if ('detail' in error && typeof error.detail === 'string') {
				return error.detail;
			}

			if ('message' in error && typeof error.message === 'string') {
				return error.message;
			}
		}

		return fallback;
	};

	const normalizeWorkspacePath = (path: string | null | undefined) => {
		if (!path) {
			return '';
		}

		if (path === '/') {
			return '/';
		}

		return path.replace(/\/+$/, '');
	};

	const getWorkspaceLeafName = (path: string | null | undefined) =>
		normalizeWorkspacePath(path).split('/').filter(Boolean).at(-1) ?? '';

	const joinWorkspacePath = (basePath: string, name: string) => {
		const normalizedBasePath = normalizeWorkspacePath(basePath);
		return normalizedBasePath === '/' ? `/${name}` : `${normalizedBasePath}/${name}`;
	};

	const getWorkspaceParentPath = (path: string) =>
		normalizeWorkspacePath(path).substring(0, normalizeWorkspacePath(path).lastIndexOf('/')) || '/';

	const getRelativeWorkspacePath = (path: string, rootPath: string) => {
		const normalizedPath = normalizeWorkspacePath(path);
		const normalizedRootPath = normalizeWorkspacePath(rootPath);

		if (!normalizedPath || !normalizedRootPath || normalizedPath === normalizedRootPath) {
			return '';
		}

		if (normalizedRootPath === '/') {
			return normalizedPath.slice(1);
		}

		return normalizedPath.startsWith(`${normalizedRootPath}/`)
			? normalizedPath.slice(normalizedRootPath.length + 1)
			: normalizedPath.replace(`${normalizedRootPath}/`, '');
	};

	const buildWorkspacePathTrail = (path: string, rootPath: string, rootLabel: string) => {
		const normalizedRootPath = normalizeWorkspacePath(rootPath);
		const trail = [
			{
				label: rootLabel || $i18n.t('Active workspace'),
				path: normalizedRootPath
			}
		];
		const relativePath = getRelativeWorkspacePath(path, rootPath);

		if (!relativePath) {
			return trail;
		}

		let currentPath = normalizedRootPath;

		for (const segment of relativePath.split('/').filter(Boolean)) {
			currentPath = joinWorkspacePath(currentPath, segment);
			trail.push({
				label: segment,
				path: currentPath
			});
		}

		return trail;
	};

	const countWorkspaceTreeNodes = (
		nodes: Array<{ path?: string; children?: Array<{ path?: string; children?: any[] }> }> = []
	): number =>
		nodes.reduce((total, node) => {
			const canCountChildren =
				typeof node.path === 'string' && workspaceTreeExpandedPaths.includes(node.path);
			return total + 1 + (canCountChildren ? countWorkspaceTreeNodes(node.children ?? []) : 0);
		}, 0);

	const getWorkspacePathHierarchy = (path: string, rootPath: string) => {
		const normalizedPath = normalizeWorkspacePath(path);
		const normalizedRootPath = normalizeWorkspacePath(rootPath);

		if (!normalizedPath || !normalizedRootPath) {
			return [];
		}

		const pathHierarchy = [normalizedRootPath];
		let currentPath = normalizedRootPath;
		const relativePath = getRelativeWorkspacePath(normalizedPath, normalizedRootPath);

		for (const segment of relativePath.split('/').filter(Boolean)) {
			currentPath = joinWorkspacePath(currentPath, segment);
			pathHierarchy.push(currentPath);
		}

		return pathHierarchy;
	};

	const createWorkspaceSurfaceItem = (
		filePath: string,
		size: number | null = null
	): HermesWorkspaceSurfaceItem => ({
		id: `workspace:${filePath}`,
		name: getWorkspaceLeafName(filePath) || $i18n.t('Untitled workspace file'),
		source: 'workspace',
		type: 'file',
		reference: filePath,
		url: getHermesWorkspaceFileUrl(filePath),
		size,
		previewable: true
	});

	const persistWorkspaceContinuityState = (patch: Partial<typeof workspaceContinuityState>) => {
		workspaceContinuityState = {
			...workspaceContinuityState,
			...patch
		};
		savedWorkspaceStateByChatKey[activeChatKey] = workspaceContinuityState;
	};

	const updateWorkspaceTreeLoadingState = (path: string, isLoading: boolean) => {
		const normalizedPath = normalizeHermesWorkspaceTreePath(path);

		if (!normalizedPath) {
			return;
		}

		if (isLoading) {
			if (!workspaceTreeLoadingPaths.includes(normalizedPath)) {
				workspaceTreeLoadingPaths = [...workspaceTreeLoadingPaths, normalizedPath];
			}
			return;
		}

		workspaceTreeLoadingPaths = workspaceTreeLoadingPaths.filter(
			(loadingPath) => loadingPath !== normalizedPath
		);
	};

	const cacheWorkspaceBrowseEntries = (
		basePath: string,
		entries: HermesWorkspaceBrowseEntry[] | null | undefined
	) => {
		const normalizedBasePath = normalizeWorkspacePath(basePath);

		if (!normalizedBasePath) {
			return;
		}

		workspaceTreeEntriesByPath = {
			...workspaceTreeEntriesByPath,
			[normalizedBasePath]: entries ?? []
		};
	};

	const getWorkspaceEntryByPath = (path: string) => {
		const normalizedPath = normalizeWorkspacePath(path);
		const parentPath = getWorkspaceParentPath(normalizedPath);
		const entryName = getWorkspaceLeafName(normalizedPath);

		if (!parentPath || !entryName) {
			return null;
		}

		return (workspaceTreeEntriesByPath[parentPath] ?? []).find((entry) => entry.name === entryName) ?? null;
	};

	const getFileContentUrl = (item: HermesWorkspaceSurfaceItem) => {
		if (item.fileId) {
			return `${WEBUI_API_BASE_URL}/files/${item.fileId}/content`;
		}

		if (item.url) {
			if (item.url.startsWith('http') || item.url.startsWith('/api/')) {
				return item.url;
			}

			return `${WEBUI_API_BASE_URL}/files/${item.url}/content`;
		}

		return null;
	};

	const handleSwitchWorkspace = async (workspace: HermesWorkspace) => {
		if (!workspace || workspace.is_active || switchingWorkspacePath || hasActiveTasks) {
			return;
		}

		if (typeof localStorage === 'undefined' || !localStorage.token) {
			toast.error($i18n.t('Failed to switch Hermes workspace.'));
			return;
		}

		switchingWorkspacePath = workspace.path;

		try {
			const nextWorkspaces = await switchHermesWorkspace(localStorage.token, workspace.path);
			onHermesWorkspaceSwitched(nextWorkspaces);
			toast.success($i18n.t('Switched Hermes workspace.'));
		} catch (error) {
			console.error(error);
			toast.error(getErrorMessage(error, $i18n.t('Failed to switch Hermes workspace.')));
		} finally {
			switchingWorkspacePath = null;
		}
	};

	const loadWorkspaceBranch = async (
		path?: string | null,
		{
			focus = false,
			force = false
		}: {
			focus?: boolean;
			force?: boolean;
		} = {}
	) => {
		const normalizedPath = normalizeWorkspacePath(path ?? activeHermesWorkspace?.path ?? '');

		if (!normalizedPath) {
			return null;
		}

		if (
			!force &&
			Object.prototype.hasOwnProperty.call(workspaceTreeEntriesByPath, normalizedPath)
		) {
			const cachedEntries = workspaceTreeEntriesByPath[normalizedPath] ?? [];
			if (focus) {
				workspaceBrowsePath = normalizedPath;
				workspaceBrowseEntries = cachedEntries;
			}
			return {
				root_path: workspaceBrowseRootPath || activeHermesWorkspace?.path || normalizedPath,
				current_path: normalizedPath,
				entries: cachedEntries
			};
		}

		if (
			typeof localStorage === 'undefined' ||
			!localStorage.token ||
			!activeHermesWorkspace?.path
		) {
			return null;
		}

		updateWorkspaceTreeLoadingState(normalizedPath, true);

		if (focus) {
			workspaceBrowseLoading = true;
			workspaceBrowseError = '';
		}

		try {
			const browseResponse = await getHermesWorkspaceBrowse(localStorage.token, normalizedPath);
			const currentPath = normalizeWorkspacePath(browseResponse.current_path) || normalizedPath;
			const nextEntries = browseResponse.entries ?? [];

			cacheWorkspaceBrowseEntries(currentPath, nextEntries);
			workspaceBrowseRootPath = browseResponse.root_path;

			if (focus) {
				workspaceBrowseEntries = nextEntries;
				workspaceBrowsePath = currentPath;
			}

			return {
				...browseResponse,
				current_path: currentPath,
				entries: nextEntries
			};
		} catch (error) {
			console.error(error);
			if (focus) {
				workspaceBrowseEntries = [];
				workspaceBrowseError = getErrorMessage(
					error,
					$i18n.t('Failed to load Hermes workspace files.')
				);
			}
			return null;
		} finally {
			updateWorkspaceTreeLoadingState(normalizedPath, false);
			if (focus) {
				workspaceBrowseLoading = false;
			}
		}
	};

	const loadWorkspaceBrowse = async (path?: string | null, force = false) => {
		const browseResponse = await loadWorkspaceBranch(path, {
			focus: true,
			force
		});

		if (browseResponse) {
			persistWorkspaceContinuityState({
				rootPath: browseResponse.root_path ?? activeHermesWorkspace?.path ?? null,
				browsePath: browseResponse.current_path ?? path ?? activeHermesWorkspace?.path ?? null
			});
		}

		workspaceBrowseLoaded = true;
		return browseResponse;
	};

	const hydrateWorkspaceTree = async (path?: string | null) => {
		const rootPath = normalizeWorkspacePath(activeHermesWorkspace?.path ?? '');
		const targetPath = normalizeWorkspacePath(path ?? rootPath);

		if (!rootPath) {
			workspaceBrowseLoaded = true;
			return;
		}

		const hierarchy = getWorkspacePathHierarchy(targetPath || rootPath, rootPath);
		workspaceTreeExpandedPaths = [...new Set(hierarchy)];
		workspaceBrowseLoaded = false;

		const rootBrowse = await loadWorkspaceBrowse(rootPath, true);
		if (!rootBrowse) {
			workspaceBrowseLoaded = true;
			return;
		}

		if (targetPath && targetPath !== rootPath) {
			for (const branchPath of hierarchy.slice(1)) {
				const browseResponse = await loadWorkspaceBranch(branchPath, {
					focus: branchPath === targetPath,
					force: true
				});

				if (!browseResponse) {
					break;
				}
			}
		}

		workspaceBrowseRootPath = rootBrowse.root_path ?? rootPath;
		workspaceBrowsePath = targetPath || rootPath;
		workspaceBrowseEntries = workspaceTreeEntriesByPath[workspaceBrowsePath] ?? rootBrowse.entries ?? [];
		persistWorkspaceContinuityState({
			rootPath: workspaceBrowseRootPath || rootPath,
			browsePath: workspaceBrowsePath || rootPath
		});
		workspaceBrowseLoaded = true;
	};

	const browseWorkspaceParent = async () => {
		if (!workspaceBrowsePath || !workspaceBrowseRootPath || !hasWorkspaceParent) {
			return;
		}

		const parentPath = getWorkspaceParentPath(workspaceBrowsePath);
		const normalizedParent =
			parentPath.length < workspaceBrowseRootPath.length ? workspaceBrowseRootPath : parentPath;

		selectedWorkspaceItem = null;
		persistWorkspaceContinuityState({
			previewReference: null
		});
		workspaceTreeExpandedPaths = [...new Set(getWorkspacePathHierarchy(normalizedParent, workspaceBrowseRootPath))];
		await loadWorkspaceBrowse(normalizedParent);
	};

	const browseWorkspaceTrail = async (path: string) => {
		if (!path || normalizeWorkspacePath(path) === normalizeWorkspacePath(currentWorkspacePath)) {
			return;
		}

		selectedWorkspaceItem = null;
		persistWorkspaceContinuityState({
			previewReference: null
		});
		if (workspaceBrowseRootPath) {
			workspaceTreeExpandedPaths = [
				...new Set(getWorkspacePathHierarchy(path, workspaceBrowseRootPath))
			];
		}
		await loadWorkspaceBrowse(path);
	};

	const toggleWorkspaceDirectory = async (path: string) => {
		const normalizedPath = normalizeWorkspacePath(path);
		const normalizedRootPath = normalizeWorkspacePath(
			workspaceBrowseRootPath || activeHermesWorkspace?.path || normalizedPath
		);

		if (!normalizedPath) {
			return;
		}

		selectedWorkspaceItem = null;
		persistWorkspaceContinuityState({
			previewReference: null,
			browsePath: normalizedPath
		});

		const isExpanded = workspaceTreeExpandedPaths.includes(normalizedPath);

		if (isExpanded && normalizedPath !== normalizedRootPath) {
			workspaceTreeExpandedPaths = workspaceTreeExpandedPaths.filter(
				(expandedPath) =>
					expandedPath !== normalizedPath &&
					!expandedPath.startsWith(`${normalizedPath}/`)
			);
			workspaceBrowsePath = normalizedPath;
			workspaceBrowseEntries = workspaceTreeEntriesByPath[normalizedPath] ?? [];
			return;
		}

		workspaceTreeExpandedPaths = [
			...new Set([
				...workspaceTreeExpandedPaths,
				...getWorkspacePathHierarchy(normalizedPath, normalizedRootPath)
			])
		];
		await loadWorkspaceBrowse(normalizedPath);
	};

	const openWorkspacePath = async (
		entryPath: string,
		type: HermesWorkspaceBrowseEntry['type'],
		size: number | null = null
	) => {
		const normalizedEntryPath = normalizeHermesWorkspaceTreePath(entryPath);

		if (type === 'directory') {
			await toggleWorkspaceDirectory(normalizedEntryPath);
			return;
		}

		selectedItemId = null;
		savedSelectionByChatKey[activeChatKey] = null;
		selectedWorkspaceItem = createWorkspaceSurfaceItem(normalizedEntryPath, size);
		persistWorkspaceContinuityState({
			rootPath: workspaceBrowseRootPath || activeHermesWorkspace?.path || null,
			browsePath: currentWorkspacePath || activeHermesWorkspace?.path || null,
			previewReference: normalizedEntryPath,
			lastFocusedReference: normalizedEntryPath
		});
	};

	const refreshWorkspaceTree = async () => {
		const targetPath =
			currentWorkspacePath || workspaceBrowseRootPath || activeHermesWorkspace?.path || null;

		if (!targetPath) {
			return;
		}

		await loadWorkspaceBrowse(targetPath, true);
	};

	const selectItem = (item: HermesWorkspaceSurfaceItem) => {
		selectedWorkspaceItem = null;
		selectedItemId = item.id;
		savedSelectionByChatKey[activeChatKey] = item.id;
		persistWorkspaceContinuityState({
			previewReference: null
		});
	};

	const closePreview = () => {
		selectedItemId = null;
		selectedWorkspaceItem = null;
		loadedItemId = null;
		savedSelectionByChatKey[activeChatKey] = null;
		persistWorkspaceContinuityState({
			previewReference: null
		});
		clearPreviewState();
	};

	const loadOfficePreview = async (name: string, arrayBuffer: ArrayBuffer) => {
		const ext = name.split('.').pop()?.toLowerCase() ?? '';

		if (ext === 'docx') {
			const [mammoth, DOMPurify] = await Promise.all([import('mammoth'), import('dompurify')]);
			const result = await mammoth.convertToHtml({ arrayBuffer });
			fileOfficeHtml = DOMPurify.default.sanitize(result.value);
			return;
		}

		if (ext === 'xlsx') {
			const XLSX = await import('xlsx');
			const { excelToTable } = await import('$lib/utils/excelToTable');
			const workbook = XLSX.read(new Uint8Array(arrayBuffer), { type: 'array' });
			excelWorkbook = workbook;
			excelSheetNames = workbook.SheetNames;
			if (excelSheetNames.length > 0) {
				selectedExcelSheet = excelSheetNames[0];
				const result = await excelToTable(workbook.Sheets[selectedExcelSheet]);
				fileOfficeHtml = result.html;
			}
			return;
		}

		if (ext === 'pptx') {
			const { pptxToImages } = await import('$lib/utils/pptxToHtml');
			const result = await pptxToImages(arrayBuffer);
			fileOfficeSlides = result.images;
			currentSlide = 0;
		}
	};

	const applyBlobPreview = async (
		name: string,
		blob: Blob,
		contentType?: string | null
	): Promise<void> => {
		const previewMode = getHermesWorkspacePreviewMode(name, contentType);

		if (previewMode === 'image') {
			fileImageUrl = URL.createObjectURL(blob);
			return;
		}

		if (previewMode === 'video') {
			fileVideoUrl = URL.createObjectURL(blob);
			return;
		}

		if (previewMode === 'audio') {
			fileAudioUrl = URL.createObjectURL(blob);
			return;
		}

		if (previewMode === 'pdf') {
			filePdfData = await blob.arrayBuffer();
			return;
		}

		if (previewMode === 'sqlite') {
			fileSqliteData = await blob.arrayBuffer();
			return;
		}

		if (previewMode === 'office') {
			await loadOfficePreview(name, await blob.arrayBuffer());
			return;
		}

		if (previewMode === 'text') {
			fileContent = await blob.text();
			return;
		}

		previewUnsupported = true;
	};

	const fetchRemoteBlob = async (url: string) => {
		const sameOrigin =
			typeof window !== 'undefined' &&
			new URL(url, window.location.origin).origin === window.location.origin;
		const headers =
			sameOrigin && typeof localStorage !== 'undefined' && localStorage.token
				? {
						authorization: `Bearer ${localStorage.token}`
					}
				: undefined;

		const response = await fetch(
			url,
			sameOrigin
				? {
						credentials: 'include',
						headers
					}
				: undefined
		);
		if (!response.ok) {
			throw new Error('Failed to fetch generated file');
		}

		return {
			blob: await response.blob(),
			contentType: response.headers.get('content-type') || null
		};
	};

	const loadSelectedItem = async (item: HermesWorkspaceSurfaceItem) => {
		const requestId = ++loadRequestId;
		selectedItemLoading = true;
		clearPreviewState();

		try {
			if (item.content !== null && item.content !== undefined) {
				fileContent = item.content;
				return;
			}

			if (item.source === 'chat' && item.fileId) {
				if (typeof localStorage === 'undefined' || !localStorage.token) {
					throw new Error('Missing auth token');
				}

				const file = await getFileById(localStorage.token, item.fileId);
				if (requestId !== loadRequestId) {
					return;
				}

				const contentType = file?.meta?.content_type ?? item.contentType ?? null;
				if (getHermesWorkspacePreviewMode(item.name, contentType) === 'text') {
					const inlineContent =
						typeof file?.data?.content === 'string' ? file.data.content : (item.content ?? null);
					if (inlineContent !== null) {
						fileContent = inlineContent;
						return;
					}
				}

				const arrayBuffer = await getFileContentById(item.fileId);
				if (requestId !== loadRequestId) {
					return;
				}

				if (!arrayBuffer) {
					throw new Error('No file content');
				}

				await applyBlobPreview(
					item.name,
					new Blob([arrayBuffer], {
						type: contentType || 'application/octet-stream'
					}),
					contentType
				);
				return;
			}

			if (item.url) {
				const { blob, contentType } = await fetchRemoteBlob(item.url);
				if (requestId !== loadRequestId) {
					return;
				}

				await applyBlobPreview(item.name, blob, contentType ?? item.contentType);
				return;
			}

			previewUnsupported = true;
		} catch (error) {
			console.error(error);
			if (requestId === loadRequestId) {
				previewError = $i18n.t('Preview is not available for this file right now.');
			}
		} finally {
			if (requestId === loadRequestId) {
				selectedItemLoading = false;
			}
		}
	};

	const refreshSelectedItem = async () => {
		if (!selectedItem) {
			return;
		}

		loadedItemId = null;
		await loadSelectedItem(selectedItem);
	};

	const copySelectedReference = async () => {
		if (!selectedItem?.reference) {
			return;
		}

		const copied = await copyToClipboard(selectedItem.reference);
		toast[copied ? 'success' : 'error'](
			$i18n.t(copied ? 'Copied to clipboard' : 'Failed to copy to clipboard')
		);
	};

	const openSelectedItem = () => {
		if (!selectedItem) {
			return;
		}

		if (selectedItem.content && !getFileContentUrl(selectedItem)) {
			void copySelectedReference();
			return;
		}

		const target = getFileContentUrl(selectedItem);
		if (!target || typeof window === 'undefined') {
			return;
		}

		window.open(target, '_blank', 'noopener,noreferrer');
	};

	const getAttachPayload = async (item: HermesWorkspaceSurfaceItem) => {
		if (item.content !== null && item.content !== undefined) {
			return {
				blob: new Blob([item.content], {
					type: item.contentType || 'text/plain'
				}),
				contentType: item.contentType || 'text/plain'
			};
		}

		if (item.fileId) {
			const arrayBuffer = await getFileContentById(item.fileId);
			if (!arrayBuffer) {
				throw new Error('No file content');
			}

			return {
				blob: new Blob([arrayBuffer], {
					type: item.contentType || 'application/octet-stream'
				}),
				contentType: item.contentType || 'application/octet-stream'
			};
		}

		const target = getFileContentUrl(item);
		if (!target) {
			throw new Error('No file target');
		}

		return fetchRemoteBlob(target);
	};

	const attachSelectedItem = async () => {
		if (!selectedItem || !canAttachSelectedItem || !onAttach) {
			return;
		}

		try {
			const { blob, contentType } = await getAttachPayload(selectedItem);
			await onAttach(
				blob,
				selectedItem.name,
				contentType || blob.type || 'application/octet-stream'
			);
		} catch (error) {
			console.error(error);
			toast.error($i18n.t('Failed to attach file'));
		}
	};

	onDestroy(() => {
		loadRequestId += 1;
		clearPreviewState();
	});
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	{#if availableHermesWorkspaces.length > 1}
		<div
			class="mx-2 mb-2 rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
		>
			<div
				class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
			>
				{$i18n.t('Workspaces')}
			</div>
			<div class="mt-1 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
				{$i18n.t('Switch the active Hermes workspace without leaving the current chat shell.')}
			</div>

			<div class="mt-2 flex flex-col gap-1.5">
				{#each availableHermesWorkspaces as workspace}
					<button
						type="button"
						class="w-full rounded-lg border px-2.5 py-2 text-left transition disabled:cursor-not-allowed disabled:opacity-60 {workspace.is_active
							? 'border-gray-200 bg-gray-50/80 dark:border-gray-700 dark:bg-gray-800/60'
							: 'border-gray-100/80 bg-white/40 hover:bg-gray-50/70 dark:border-gray-800/80 dark:bg-gray-900/30 dark:hover:bg-gray-800/40'}"
						disabled={switchingWorkspacePath !== null || hasActiveTasks || workspace.is_active}
						on:click={() => handleSwitchWorkspace(workspace)}
					>
						<div class="flex items-start justify-between gap-2">
							<div class="min-w-0">
								<div class="line-clamp-1 text-xs font-medium text-gray-700 dark:text-gray-200">
									{workspace.name}
								</div>
								<div class="mt-0.5 line-clamp-1 text-[11px] text-gray-400 dark:text-gray-500">
									{workspace.path}
								</div>
							</div>

							<div class="flex shrink-0 flex-wrap justify-end gap-1">
								{#if switchingWorkspacePath === workspace.path}
									<div
										class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-300"
									>
										{$i18n.t('Switching')}...
									</div>
								{:else if workspace.path === activeHermesWorkspace?.path}
									<div
										class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-300"
									>
										{$i18n.t('Active workspace')}
									</div>
								{/if}
							</div>
						</div>
					</button>
				{/each}
			</div>

			{#if hasActiveTasks}
				<div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
					{$i18n.t('Cannot switch workspaces while a task is running.')}
				</div>
			{/if}
		</div>
	{/if}

	{#if !canBrowseWorkspace && workspaceItems.length === 0 && workspaceBrowserEntries.length === 0 && !workspaceBrowseLoading && !workspaceBrowseError && workspaceBrowseLoaded}
		<div
			class="mx-2 flex flex-1 min-h-0 flex-col justify-center rounded-xl border border-gray-100/80 bg-white/80 px-3 py-3 dark:border-gray-800/80 dark:bg-gray-900/40"
		>
			<HermesWorkspaceGuideRow
				title={$i18n.t('Workspace ready for this chat')}
				description={$i18n.t(
					'Workspace tree, linked outputs, and linked attachments will surface here as the conversation produces them.'
				)}
				metaItems={[$i18n.t('Workspace tree'), $i18n.t('Linked outputs'), $i18n.t('Linked attachments')]}
			/>
			<div class="px-3 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
				{$i18n.t('This surface stays first-class even before the session writes anything.')}
			</div>
		</div>
	{:else if selectedItem}
		<div
			class="mx-2 rounded-xl border border-gray-100/80 bg-white/90 dark:border-gray-800/80 dark:bg-gray-900/50"
		>
			<div class="flex flex-wrap gap-1.5 border-b border-gray-100 px-3 py-2 dark:border-gray-800">
				<button
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={closePreview}
				>
					{$i18n.t('Back to list')}
				</button>
				<button
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={openSelectedItem}
					disabled={!canOpenSelectedItem}
				>
					{$i18n.t('Open')}
				</button>
				<button
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={attachSelectedItem}
					disabled={!canAttachSelectedItem}
				>
					{$i18n.t('Attach to chat')}
				</button>
				<button
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={copySelectedReference}
					disabled={!selectedItem.reference}
				>
					{$i18n.t('Copy path')}
				</button>
				<button
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={refreshSelectedItem}
				>
					{$i18n.t('Refresh')}
				</button>
			</div>

			<div class="border-b border-gray-100 px-3 py-2 dark:border-gray-800">
				<div class="line-clamp-1 text-sm font-medium text-gray-800 dark:text-gray-100">
					{selectedItem.name}
				</div>
				{#if selectedItem.reference}
					<div class="mt-1 line-clamp-1 text-[11px] text-gray-400 dark:text-gray-500">
						{$i18n.t('Path: {{PATH}}', { PATH: selectedItem.reference })}
					</div>
				{/if}

				{#if selectedItemMetaItems.length > 0}
					<div class="mt-1 flex flex-wrap gap-1.5">
						{#each selectedItemMetaItems as metaItem}
							<div
								class="rounded-full bg-gray-50 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-950/70 dark:text-gray-400"
							>
								<span class="block max-w-full truncate">{metaItem}</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<div class="flex min-h-[18rem] flex-1 overflow-hidden">
				{#if selectedItemLoading}
					<div class="flex h-full w-full items-center justify-center">
						<Spinner className="size-4" />
					</div>
				{:else if previewError || previewUnsupported}
					<div class="w-full p-3">
						<HermesWorkspaceGuideRow
							title={selectedItem.name}
							description={previewError ||
								$i18n.t('Preview is not available for this file type yet.')}
							metaItems={selectedItemMetaItems}
						/>
					</div>
				{:else}
					<FilePreview
						bind:currentSlide
						selectedFile={selectedItem.name}
						fileLoading={selectedItemLoading}
						{fileContent}
						{fileImageUrl}
						{fileVideoUrl}
						{fileAudioUrl}
						{filePdfData}
						{fileSqliteData}
						{fileOfficeHtml}
						{fileOfficeSlides}
						{excelSheetNames}
						{selectedExcelSheet}
						onSheetChange={async (sheet) => {
							if (!excelWorkbook) {
								return;
							}

							selectedExcelSheet = sheet;
							const { excelToTable } = await import('$lib/utils/excelToTable');
							const result = await excelToTable(excelWorkbook.Sheets[sheet]);
							fileOfficeHtml = result.html;
						}}
					/>
				{/if}
			</div>
		</div>
	{:else}
		<div class="flex flex-1 min-h-0 flex-col overflow-hidden px-2">
			{#if canBrowseWorkspace}
				<div class="flex flex-1 min-h-0 flex-col pb-2">
					<div
						class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-gray-100/80 bg-white/85 dark:border-gray-800/80 dark:bg-gray-900/45"
					>
						<div class="border-b border-gray-100 px-3 py-2.5 dark:border-gray-800">
							<div class="flex items-start justify-between gap-2">
								<div class="min-w-0">
									<div
										class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
									>
										{$i18n.t('Active workspace tree')}
									</div>
									<div class="mt-1 flex flex-wrap gap-1.5">
										{#each workspaceBrowserMeta as metaItem}
											<div
												class="rounded-full bg-gray-50 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-950/70 dark:text-gray-400"
											>
												<span class="block max-w-full truncate">{metaItem}</span>
											</div>
										{/each}
									</div>
								</div>

								<div class="flex shrink-0 flex-wrap gap-1.5">
									{#if hasWorkspaceParent}
										<button
											class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
											on:click={browseWorkspaceParent}
										>
											{$i18n.t('Back')}
										</button>
									{/if}
									<button
										class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
										on:click={refreshWorkspaceTree}
									>
										{$i18n.t('Refresh')}
									</button>
								</div>
							</div>

							{#if workspacePathTrail.length > 0}
								<div class="mt-2 overflow-x-auto">
									<div
										class="flex min-w-max items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400"
									>
										<div class="shrink-0 font-medium text-gray-400 dark:text-gray-500">
											{$i18n.t('Path')}
										</div>
										{#each workspacePathTrail as segment, index}
											<div class="shrink-0 text-gray-300 dark:text-gray-700">/</div>
											<button
												class="shrink-0 rounded-full px-2 py-0.5 transition {index ===
												workspacePathTrail.length - 1
													? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'
													: 'bg-transparent text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200'}"
												disabled={index === workspacePathTrail.length - 1}
												on:click={() => browseWorkspaceTrail(segment.path)}
											>
												{segment.label}
											</button>
										{/each}
									</div>
								</div>
							{/if}
						</div>

						{#if !workspaceBrowseLoaded || workspaceBrowseLoading}
							<div class="flex flex-1 min-h-0 items-center justify-center py-5">
								<Spinner className="size-4" />
							</div>
						{:else if workspaceBrowseError}
							<div class="flex flex-1 min-h-0 px-3 py-3 text-xs text-gray-500 dark:text-gray-400">
								{workspaceBrowseError}
							</div>
						{:else if workspaceTreeNodes.length === 0}
							<div
								class="m-3 flex flex-1 min-h-0 items-center justify-center rounded-xl border border-dashed border-gray-200/80 bg-gray-50/70 px-4 py-4 text-center text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900/30 dark:text-gray-400"
							>
								{$i18n.t('This workspace tree is empty. Hermes will surface folders and files here once the session writes them.')}
							</div>
						{:else}
							{#if workspaceBrowserEntries.length === 0}
								<div class="border-b border-gray-100 px-3 py-2 text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
									{$i18n.t(
										'This folder is empty. Keep browsing the tree or return to the workspace root.'
									)}
								</div>
							{/if}

							<div class="flex-1 min-h-0 overflow-y-auto px-1 py-1.5">
								<HermesWorkspaceTree
									nodes={workspaceTreeNodes}
									expandedPaths={workspaceTreeExpandedPaths}
									loadingPaths={workspaceTreeLoadingPaths}
									selectedPath={selectedWorkspaceTreePath}
									activeDirectoryPath={currentWorkspacePath}
									rememberedPath={rememberedWorkspaceTreePath}
									onToggleDirectory={toggleWorkspaceDirectory}
									onSelectFile={(path) => {
										const entry = getWorkspaceEntryByPath(path);
										void openWorkspacePath(path, 'file', entry?.size ?? null);
									}}
								/>
							</div>
						{/if}
					</div>
				</div>
			{/if}

			{#if generatedWorkspaceItems.length > 0 || chatWorkspaceItems.length > 0}
				<div class="shrink-0 space-y-2 pb-2">
					{#if generatedWorkspaceItems.length > 0}
						<HermesWorkspaceGuideRow
							title={$i18n.t('Linked outputs')}
							description={$i18n.t(
								'Files generated by Hermes during this chat. Open the latest output or browse them in the active workspace tree above.'
							)}
							metaItems={generatedWorkspaceMeta}
						>
							<svelte:fragment slot="actions">
								<button
									class="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-100 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900"
									on:click={() => latestGeneratedWorkspaceItem && selectItem(latestGeneratedWorkspaceItem)}
									disabled={!latestGeneratedWorkspaceItem}
								>
									{$i18n.t('Open latest output')}
								</button>
							</svelte:fragment>
						</HermesWorkspaceGuideRow>
					{/if}

					{#if chatWorkspaceItems.length > 0}
						<HermesWorkspaceGuideRow
							title={$i18n.t('Linked attachments')}
							description={$i18n.t(
								'Files already attached to this chat. Open the latest attachment here or keep them linked to the conversation.'
							)}
							metaItems={chatWorkspaceMeta}
						>
							<svelte:fragment slot="actions">
								<button
									class="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-100 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900"
									on:click={() => latestChatWorkspaceItem && selectItem(latestChatWorkspaceItem)}
									disabled={!latestChatWorkspaceItem}
								>
									{$i18n.t('Open latest attachment')}
								</button>
							</svelte:fragment>
						</HermesWorkspaceGuideRow>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
