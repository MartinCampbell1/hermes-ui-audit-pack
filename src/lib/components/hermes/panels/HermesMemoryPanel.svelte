<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { type HermesProfile } from '$lib/apis/hermes';
	import { deleteMemoryById, getMemories, type MemoryItem } from '$lib/apis/memories';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import AddMemoryModal from '$lib/components/chat/Settings/Personalization/AddMemoryModal.svelte';
	import EditMemoryModal from '$lib/components/chat/Settings/Personalization/EditMemoryModal.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import {
		hermesProfilesLoaded,
		hermesProfilesLoading,
		hermesProfilesStore
	} from '$lib/stores';
	import { ensureHermesContextBundle } from '$lib/utils/hermesContext';

	const i18n = getContext<any>('i18n');

	// TODO(21st): Replace this stopgap local panel pattern with a 21st.dev-derived micro-surface once MCP auth is fixed.

	export let active = false;

	type MemoryGroup = {
		id: string;
		label: string;
		items: MemoryItem[];
	};

	let memoriesLoaded = false;
	let memoriesLoading = false;
	let previousActive = false;
	let profileLoadError = '';
	let query = '';
	let memories: MemoryItem[] = [];
	let showAddMemoryModal = false;
	let showEditMemoryModal = false;
	let showDeleteConfirm = false;
	let selectedMemory: MemoryItem | null = null;

	const normalizeTimestamp = (value: number | null | undefined) =>
		typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

	const getErrorMessage = (error: any, fallback: string) => {
		if (typeof error === 'string') {
			return error;
		}

		return error?.detail ?? error?.message ?? fallback;
	};

	const formatDateTime = (timestamp: number | null | undefined) => {
		const normalizedTimestamp = normalizeTimestamp(timestamp);
		if (!normalizedTimestamp) {
			return '';
		}

		return new Intl.DateTimeFormat(undefined, {
			dateStyle: 'medium',
			timeStyle: 'short'
		}).format(new Date(normalizedTimestamp * 1000));
	};

	const groupMemoriesByMonth = (items: MemoryItem[]) => {
		const grouped = new Map<string, MemoryGroup>();

		for (const item of items) {
			const sortTimestamp =
				normalizeTimestamp(item.updated_at) ?? normalizeTimestamp(item.created_at) ?? 0;
			const groupDate = new Date(sortTimestamp * 1000);
			const groupId = `${groupDate.getFullYear()}-${groupDate.getMonth() + 1}`;
			const label = new Intl.DateTimeFormat(undefined, {
				month: 'long',
				year: 'numeric'
			}).format(groupDate);

			if (!grouped.has(groupId)) {
				grouped.set(groupId, {
					id: groupId,
					label,
					items: []
				});
			}

			grouped.get(groupId)?.items.push(item);
		}

		return Array.from(grouped.values());
	};

	const sortMemories = (items: MemoryItem[]) =>
		[...items].sort((left, right) => {
			const rightTimestamp =
				normalizeTimestamp(right.updated_at) ?? normalizeTimestamp(right.created_at) ?? 0;
			const leftTimestamp =
				normalizeTimestamp(left.updated_at) ?? normalizeTimestamp(left.created_at) ?? 0;

			return rightTimestamp - leftTimestamp;
		});

	const loadMemories = async (force = false) => {
		if (memoriesLoading || (memoriesLoaded && !force)) {
			return;
		}

		if (typeof localStorage === 'undefined') {
			return;
		}

		memoriesLoading = true;

		try {
			const nextMemories = await getMemories(localStorage.token).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			memories = sortMemories((nextMemories ?? []).filter(Boolean));
		} finally {
			memoriesLoaded = true;
			memoriesLoading = false;
		}
	};

	const loadProfileContext = async (force = false) => {
		if (typeof localStorage === 'undefined') {
			return;
		}

		profileLoadError = '';

		try {
			await ensureHermesContextBundle(localStorage.token, {
				force,
				includeProfiles: true
			});
			if (!$hermesProfilesStore) {
				profileLoadError = $i18n.t('Profile context unavailable.');
			}
		} catch (error) {
			profileLoadError = getErrorMessage(error, $i18n.t('Profile context unavailable.'));
		}
	};

	$: filteredMemories = query
		? memories.filter((memory) => memory.content?.toLowerCase().includes(query.toLowerCase()))
		: memories;
	$: memoryGroups = groupMemoriesByMonth(filteredMemories);
	$: activeHermesProfile =
		($hermesProfilesStore?.items?.find((profile) => profile.is_active) as HermesProfile | undefined) ??
		$hermesProfilesStore?.items?.[0] ??
		null;
	$: profileMemoryEnabled = !!(
		activeHermesProfile?.memory_enabled || activeHermesProfile?.has_memory
	);
	$: userProfileEnabled = !!(
		activeHermesProfile?.user_profile_enabled || activeHermesProfile?.has_user_profile
	);
	$: loadedMemoryCount = memories.length;
	$: visibleMemoryCount = filteredMemories.length;
	$: memoryContextChips = [
		profileMemoryEnabled ? $i18n.t('Profile memory enabled') : $i18n.t('Profile memory disabled'),
		userProfileEnabled ? $i18n.t('User profile enabled') : $i18n.t('User profile disabled'),
		$i18n.t('Saved memories: {{COUNT}}', { COUNT: loadedMemoryCount }),
		$i18n.t('Visible in this list: {{COUNT}}', { COUNT: visibleMemoryCount })
	].filter(Boolean);
	$: memoryScopeStats = [
		{
			label: $i18n.t('Saved memories'),
			value: loadedMemoryCount
		},
		{
			label: $i18n.t('Visible in this list'),
			value: visibleMemoryCount
		}
	];

	$: {
		const becameActive = active && !previousActive;
		previousActive = active;

		if (becameActive) {
			if (!memoriesLoaded && !memoriesLoading) {
				loadMemories();
			}

			loadProfileContext($hermesProfilesLoaded);
		}
	}
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	<div class="flex items-center gap-2 px-2 pb-2">
		<div class="flex flex-1 items-center rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-900/70">
			<div class="mr-2 text-gray-400 dark:text-gray-500">
				<Search className="size-3.5" />
			</div>
			<input
				class="w-full bg-transparent text-sm outline-hidden"
				bind:value={query}
				placeholder={$i18n.t('Search Memories')}
			/>

			{#if query}
				<button
					type="button"
					class="ml-2 rounded-full p-1 text-gray-400 transition hover:bg-black/5 hover:text-gray-500 dark:text-gray-500 dark:hover:bg-white/5 dark:hover:text-gray-300"
					on:click={() => {
						query = '';
					}}
				>
					<XMark className="size-3.5" strokeWidth="2" />
				</button>
			{/if}
		</div>

		<button
			type="button"
			class="rounded-full bg-gray-900 px-2.5 py-1 text-[11px] font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
			on:click={() => {
				showAddMemoryModal = true;
			}}
		>
			{$i18n.t('Add Memory')}
		</button>
	</div>

	<div class="px-2 pb-2">
		<div
			class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
		>
			<div class="flex items-start justify-between gap-3">
				<div class="min-w-0">
					<div
						class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
					>
						{$i18n.t('Saved memory store')}
					</div>
					<div class="mt-1 line-clamp-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{activeHermesProfile?.name ?? $hermesProfilesStore?.active_profile ?? $i18n.t('Not set')}
					</div>

					<div class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'This is the persistent Hermes memory store for the active profile. It is not the same as per-run recalled context inside a live response.'
						)}
					</div>
				</div>

				{#if $hermesProfilesLoading}
					<div class="mt-0.5 text-gray-400">
						<Spinner className="size-4" />
					</div>
				{/if}
			</div>

			{#if memoryContextChips.length > 0}
				<div class="mt-2 flex flex-wrap gap-1.5">
					{#each memoryContextChips.slice(0, 2) as item}
						<div
							class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
						>
							{item}
						</div>
					{/each}
				</div>
			{/if}

			<div class="mt-3 grid grid-cols-2 gap-2">
				{#each memoryScopeStats as stat}
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

			<div class="mt-3 rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-950/70">
				<div class="text-[11px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
					{$i18n.t('Run-time recall')}
				</div>
				<div class="mt-1 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
					{$i18n.t('This panel shows the saved store only. Hermes decides what to recall during a live run.')}
				</div>
			</div>

			{#if profileLoadError}
				<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">{profileLoadError}</div>
			{/if}
		</div>
	</div>

	<div
		class="flex items-center justify-between gap-2 px-2 pb-2 text-[11px] text-gray-400 dark:text-gray-500"
	>
		<div>
			{#if memoriesLoading && !memoriesLoaded}
				{$i18n.t('Loading')}...
			{:else}
				{$i18n.t('Saved memories')} · {loadedMemoryCount}
			{/if}
		</div>

		{#if memoriesLoading && memoriesLoaded}
			<div class="flex items-center gap-1.5">
				<Spinner className="size-3" />
				<div>{$i18n.t('Updated')}</div>
			</div>
		{/if}
	</div>

	<div class="flex-1 min-h-0 overflow-y-auto px-1 pb-2">
		{#if memoriesLoading && !memoriesLoaded}
			<div class="flex h-24 items-center justify-center">
				<Spinner className="size-4" />
			</div>
		{:else if memoryGroups.length === 0}
			<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
				{#if query}
					{$i18n.t('No saved memories match the current search.')}
				{:else if loadedMemoryCount === 0 && $hermesProfilesLoaded && !profileMemoryEnabled}
					{$i18n.t('Profile memory is disabled. The saved memory store is also empty right now.')}
				{:else if loadedMemoryCount === 0}
					{$i18n.t('No saved memories yet.')}
				{:else}
					{$i18n.t('No memories are visible right now.')}
				{/if}
			</div>
		{:else}
			<div class="flex flex-col gap-3">
				{#each memoryGroups as group (group.id)}
					<section>
						<div class="flex items-center justify-between px-2 pb-1">
							<div
								class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
							>
								{group.label}
							</div>
							<div class="text-[11px] text-gray-400 dark:text-gray-500">{group.items.length}</div>
						</div>

						<div class="flex flex-col gap-1.5">
							{#each group.items as memory (memory.id)}
								<div
									class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 transition hover:bg-gray-50 dark:border-gray-800/80 dark:bg-gray-900/50 dark:hover:bg-gray-900"
								>
									<div class="flex items-start justify-between gap-3">
										<button
											type="button"
											class="min-w-0 flex-1 text-left"
											on:click={() => {
												selectedMemory = memory;
												showEditMemoryModal = true;
											}}
										>
											<div class="line-clamp-2 text-sm leading-6 text-gray-800 dark:text-gray-100">
												{memory.content}
											</div>
											<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
												{$i18n.t('Updated at')}: {formatDateTime(memory.updated_at)}
											</div>

											{#if normalizeTimestamp(memory.created_at) && memory.created_at !== memory.updated_at}
												<div class="text-[11px] text-gray-400 dark:text-gray-500">
													{$i18n.t('Created at')}: {formatDateTime(memory.created_at)}
												</div>
											{/if}
										</button>

										<div class="flex shrink-0 items-center gap-1 text-gray-500 dark:text-gray-400">
											<button
												type="button"
												class="rounded-xl p-1.5 transition hover:bg-black/5 dark:hover:bg-white/5"
												on:click|stopPropagation={() => {
													selectedMemory = memory;
													showEditMemoryModal = true;
												}}
											>
												<Pencil className="size-4" />
											</button>
											<button
												type="button"
												class="rounded-xl p-1.5 transition hover:bg-black/5 dark:hover:bg-white/5"
												on:click|stopPropagation={() => {
													selectedMemory = memory;
													showDeleteConfirm = true;
												}}
											>
												<GarbageBin className="size-4" strokeWidth="1.5" />
											</button>
										</div>
									</div>
								</div>
							{/each}
						</div>
					</section>
				{/each}
			</div>
		{/if}
	</div>

	<AddMemoryModal
		bind:show={showAddMemoryModal}
		on:save={() => {
			loadMemories(true);
		}}
	/>

	<EditMemoryModal
		bind:show={showEditMemoryModal}
		memory={selectedMemory ?? {}}
		on:save={() => {
			loadMemories(true);
		}}
	/>

	<ConfirmDialog
		title={$i18n.t('Delete Memory?')}
		show={showDeleteConfirm}
		on:confirm={async () => {
			if (!selectedMemory || typeof localStorage === 'undefined') {
				showDeleteConfirm = false;
				return;
			}

			const res = await deleteMemoryById(localStorage.token, selectedMemory.id).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (res) {
				toast.success($i18n.t('Memory deleted successfully'));
				await loadMemories(true);
			}

			showDeleteConfirm = false;
		}}
		on:cancel={() => {
			showDeleteConfirm = false;
		}}
	>
		<div class="text-sm text-gray-500">
			{$i18n.t('Are you sure you want to delete this memory? This action cannot be undone.')}
		</div>
	</ConfirmDialog>
</div>
