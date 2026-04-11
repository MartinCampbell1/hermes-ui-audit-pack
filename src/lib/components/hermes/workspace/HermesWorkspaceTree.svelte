<script lang="ts">
	import { getContext } from 'svelte';
	import { formatFileSize } from '$lib/utils';
	import {
		buildHermesWorkspaceTree,
		type HermesWorkspaceTreeEntry,
		type HermesWorkspaceTreeNode
	} from '$lib/utils/hermesWorkspaceTree';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import FolderOpen from '$lib/components/icons/FolderOpen.svelte';

	export let nodes: HermesWorkspaceTreeNode[] = [];
	export let entries: HermesWorkspaceTreeEntry[] = [];
	export let basePath = '';
	export let depth = 0;
	export let expandedPaths: string[] = [];
	export let loadingPaths: string[] = [];
	export let selectedPath: string | null = null;
	export let activeDirectoryPath: string | null = null;
	export let rememberedPath: string | null = null;
	export let onToggleDirectory: (path: string) => void = () => {};
	export let onSelectFile: (path: string) => void = () => {};

	const i18n = getContext<any>('i18n');
	let resolvedNodes: HermesWorkspaceTreeNode[] = [];
	const isExpandedPath = (path: string) => expandedPaths.includes(path);
	const isLoadingPath = (path: string) => loadingPaths.includes(path);
	$: resolvedNodes = nodes.length > 0 ? nodes : buildHermesWorkspaceTree(entries, basePath);
</script>

<div role={depth === 0 ? 'tree' : 'group'} class="space-y-0.5">
	{#each resolvedNodes as node (node.path)}
		{@const isDirectory = node.type === 'directory'}
		{@const isExpanded = isDirectory && isExpandedPath(node.path)}
		{@const isLoading = isDirectory && isLoadingPath(node.path)}
		{@const isSelected = selectedPath === node.path}
		{@const isActiveDirectory = isDirectory && activeDirectoryPath === node.path}
		{@const isRemembered = !isSelected && rememberedPath === node.path}

		<div>
			<button
				type="button"
				role="treeitem"
				aria-expanded={isDirectory ? isExpanded : undefined}
				aria-current={isSelected || isActiveDirectory ? 'true' : undefined}
				class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition focus:outline-none focus:ring-2 focus:ring-gray-200/80 dark:focus:ring-gray-700/80 {isSelected
					? 'bg-gray-100 text-gray-900 dark:bg-gray-800/80 dark:text-gray-100'
					: isActiveDirectory
						? 'bg-gray-50 text-gray-800 dark:bg-gray-900/70 dark:text-gray-100'
						: 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-900/60'}"
				style={`padding-left: ${depth * 14 + 8}px;`}
				on:click={() => (isDirectory ? onToggleDirectory(node.path) : onSelectFile(node.path))}
				on:keydown={(event) => {
					if (event.key !== 'Enter' && event.key !== ' ') {
						return;
					}

					event.preventDefault();
					isDirectory ? onToggleDirectory(node.path) : onSelectFile(node.path);
				}}
			>
				<div class="flex size-4 shrink-0 items-center justify-center text-gray-400 dark:text-gray-500">
					{#if isDirectory}
						{#if isLoading}
							<Spinner className="size-3" />
						{:else if isExpanded}
							<ChevronDown className="size-3.5" />
						{:else}
							<ChevronRight className="size-3.5" />
						{/if}
					{/if}
				</div>

				<div
					class="flex size-4 shrink-0 items-center justify-center {isDirectory
						? 'text-gray-500 dark:text-gray-400'
						: 'text-gray-400 dark:text-gray-500'}"
				>
					{#if isDirectory}
						{#if isExpanded}
							<FolderOpen className="size-4" />
						{:else}
							<Folder className="size-4" />
						{/if}
					{:else}
						<Document className="size-4" />
					{/if}
				</div>

				<div class="min-w-0 flex-1">
					<div class="truncate text-[13px] font-medium leading-5">
						{node.name}
					</div>
				</div>

				{#if !isDirectory && node.size}
					<div class="shrink-0 text-[11px] text-gray-400 dark:text-gray-500">
						{formatFileSize(node.size)}
					</div>
				{/if}

				{#if isSelected}
					<div
						class="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-950/70 dark:text-gray-300"
					>
						{$i18n.t('Current')}
					</div>
				{:else if isActiveDirectory}
					<div
						class="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-950/70 dark:text-gray-300"
					>
						{$i18n.t('Open')}
					</div>
				{:else if isRemembered}
					<div
						class="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-950/70 dark:text-gray-300"
					>
						{$i18n.t('Recent')}
					</div>
				{/if}
			</button>

			{#if isDirectory && isExpanded && node.children && node.children.length > 0}
				<div class="space-y-0.5">
					<svelte:self
						nodes={node.children}
						depth={depth + 1}
						{expandedPaths}
						{loadingPaths}
						{selectedPath}
						{activeDirectoryPath}
						{rememberedPath}
						{onToggleDirectory}
						{onSelectFile}
					/>
				</div>
			{/if}
		</div>
	{/each}
</div>
