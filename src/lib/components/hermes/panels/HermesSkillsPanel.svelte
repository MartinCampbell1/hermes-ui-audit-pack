<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { type HermesProfile } from '$lib/apis/hermes';
	import { getSkillItems, toggleSkillById } from '$lib/apis/skills';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import ViewSelector from '$lib/components/workspace/common/ViewSelector.svelte';
	import {
		hermesProfilesLoaded,
		hermesProfilesLoading,
		hermesProfilesStore
	} from '$lib/stores';
	import { ensureHermesContextBundle } from '$lib/utils/hermesContext';

	const i18n = getContext<any>('i18n');
	const SKILLS_PER_PAGE = 30;

	// TODO(21st): Replace this stopgap local panel pattern with a 21st.dev-derived micro-surface once MCP auth is fixed.

	export let active = false;

	let loaded = false;
	let loading = false;
	let profileLoadError = '';
	let query = '';
	let items: any[] = [];
	let total = 0;
	let viewOption = '';
	let page = 1;
	let pendingSkillIds: string[] = [];
	let queryReloadScheduled = false;
	let lastLoadedViewOption = '';
	let lastLoadedPage = 1;
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	$: currentViewLabel =
		viewOption === 'created'
			? $i18n.t('Created by you')
			: viewOption === 'shared'
				? $i18n.t('Shared with you')
				: $i18n.t('All');
	$: hermesProfiles = $hermesProfilesStore?.items ?? [];
	$: activeHermesProfile =
		(hermesProfiles.find((profile) => profile.is_active) as HermesProfile | undefined) ??
		hermesProfiles[0] ??
		null;
	$: profileSkillCount = activeHermesProfile?.skill_count ?? null;
	$: attachedSkillCount = items.filter((skill) => skill?.is_active).length;
	$: scopeStats = [
		{
			label: $i18n.t('Profile available'),
			value: profileSkillCount ?? '—'
		},
		{
			label: $i18n.t('Visible in workspace'),
			value: total
		},
		{
			label: $i18n.t('Attached to chat'),
			value: attachedSkillCount
		}
	];

	const loadSkills = async () => {
		loading = true;

		const res = await getSkillItems(localStorage.token, query, viewOption, page).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		items = res?.items ?? [];
		total = res?.total ?? 0;
		loaded = true;
		queryReloadScheduled = false;
		lastLoadedViewOption = viewOption;
		lastLoadedPage = page;
		loading = false;
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
		} catch {
			profileLoadError = $i18n.t('Profile context unavailable.');
		}
	};

	const scheduleLoad = () => {
		clearTimeout(searchDebounceTimer);
		queryReloadScheduled = true;
		page = 1;
		searchDebounceTimer = setTimeout(() => {
			if (active) {
				loadSkills();
			} else {
				queryReloadScheduled = false;
			}
		}, 250);
	};

	const getOwnerLabel = (skill: any) => {
		return skill?.user?.name ?? skill?.user?.email ?? $i18n.t('Deleted User');
	};

	const handleViewChange = (nextViewOption: string) => {
		viewOption = nextViewOption;
		page = 1;

		if (active) {
			loadSkills();
		}
	};

	const isSkillPending = (skillId: string) => pendingSkillIds.includes(skillId);

	const setSkillPending = (skillId: string, pending: boolean) => {
		pendingSkillIds = pending
			? pendingSkillIds.includes(skillId)
				? pendingSkillIds
				: [...pendingSkillIds, skillId]
			: pendingSkillIds.filter((id) => id !== skillId);
	};

	const updateSkillState = (skillId: string, isActive: boolean) => {
		items = items.map((skill) =>
			skill.id === skillId ? { ...skill, is_active: isActive } : skill
		);
	};

	const handleToggleSkill = async (skill: any) => {
		if (!skill?.write_access || isSkillPending(skill.id)) {
			return;
		}

		const nextState = !!skill.is_active;
		const previousState = !nextState;

		setSkillPending(skill.id, true);

		try {
			await toggleSkillById(localStorage.token, skill.id);
		} catch (error) {
			updateSkillState(skill.id, previousState);
			toast.error(`${error}`);
		} finally {
			setSkillPending(skill.id, false);
		}
	};

	$: if (active && !loaded && !loading) {
		loadSkills();
	}

	$: if (active && !$hermesProfilesLoaded && !$hermesProfilesLoading) {
		loadProfileContext();
	}

	$: if (
		active &&
		loaded &&
		!loading &&
		!queryReloadScheduled &&
		(viewOption !== lastLoadedViewOption || page !== lastLoadedPage)
	) {
		loadSkills();
	}

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});
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
				placeholder={$i18n.t('Search Skills')}
				on:input={scheduleLoad}
			/>

			{#if query}
				<button
					type="button"
					class="ml-2 rounded-full p-1 text-gray-400 transition hover:bg-black/5 hover:text-gray-500 dark:text-gray-500 dark:hover:bg-white/5 dark:hover:text-gray-300"
					on:click={() => {
						query = '';
						scheduleLoad();
					}}
				>
					<XMark className="size-3.5" strokeWidth="2" />
				</button>
			{/if}
		</div>

		<div class="w-36 shrink-0">
			<ViewSelector value={viewOption} onChange={handleViewChange} />
		</div>
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
						{$i18n.t('Skill context')}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{$i18n.t('Profile skills, visible library items and attached skills')}
					</div>
					<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'Profile-available skills come from the active Hermes profile. Visible library skills are the current workspace view. Attached to chat means the skills currently enabled here.'
						)}
					</div>
				</div>

				{#if $hermesProfilesLoading}
					<div class="mt-0.5 text-gray-400">
						<Spinner className="size-4" />
					</div>
				{/if}
			</div>

			<div class="mt-3 grid grid-cols-3 gap-2">
				{#each scopeStats as stat}
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

			<div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
				{$i18n.t('Profile scope can be larger than the workspace library visible in this chat shell.')}
			</div>

			{#if profileLoadError}
				<div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500">{profileLoadError}</div>
			{/if}
		</div>
	</div>

	<div
		class="flex items-center justify-between gap-2 px-2 pb-2 text-[11px] text-gray-400 dark:text-gray-500"
	>
		<div>
			{#if loading && !loaded}
				{$i18n.t('Loading')}...
			{:else}
				{$i18n.t('Visible library skills')} · {total}
			{/if}
		</div>

		<div class="flex items-center gap-2">
			<div class="hidden sm:block">
				{$i18n.t('Filter')}: {currentViewLabel}
			</div>
			<a
				class="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
				href="/workspace/skills"
			>
				{$i18n.t('Manage in workspace')}
			</a>
			{#if loading && loaded}
				<div class="flex items-center gap-1.5">
					<Spinner className="size-3" />
					<div>{$i18n.t('Loading...')}</div>
				</div>
			{/if}
		</div>
	</div>

	<div class="flex-1 min-h-0 overflow-y-auto px-1 pb-2">
		{#if loading && !loaded}
			<div class="flex h-24 items-center justify-center">
				<Spinner className="size-4" />
			</div>
		{:else if items.length === 0}
			<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
				{#if profileSkillCount === 0}
					{$i18n.t('This profile does not expose skills yet.')}
				{:else if query || viewOption}
					{$i18n.t('No visible skills match the current filter.')}
				{:else}
					{$i18n.t('No visible skills in this workspace library.')}
				{/if}
			</div>
		{:else}
			<div class="flex flex-col gap-1.5">
				{#each items as skill (skill.id)}
					<div
						class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 transition hover:bg-gray-50 dark:border-gray-800/80 dark:bg-gray-900/50 dark:hover:bg-gray-900 {isSkillPending(
							skill.id
						)
							? 'opacity-80'
							: ''}"
					>
						<div class="flex items-start justify-between gap-3">
							<button
								type="button"
								class="min-w-0 flex-1 text-left"
								on:click={() => goto(`/workspace/skills/edit?id=${encodeURIComponent(skill.id)}`)}
							>
								<div class="flex items-center gap-2">
									<div class="line-clamp-1 text-sm font-medium text-gray-800 dark:text-gray-100">
										{skill.name}
									</div>
									{#if !skill.is_active}
										<Badge type="muted" content={$i18n.t('Inactive')} />
									{/if}
									{#if !skill.write_access}
										<Badge type="muted" content={$i18n.t('Read Only')} />
									{/if}
								</div>

								{#if skill.description}
									<div class="mt-1 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400">
										{skill.description}
									</div>
								{/if}

								<div
									class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-gray-400 dark:text-gray-500"
								>
									<div>{$i18n.t('By {{name}}', { name: getOwnerLabel(skill) })}</div>
									<div class="size-1 rounded-full bg-gray-300 dark:bg-gray-600"></div>
									<div>{$i18n.t(skill.is_active ? 'Enabled' : 'Disabled')}</div>
								</div>
							</button>

							{#if skill.write_access}
								<div class="flex shrink-0 items-center gap-2">
									{#if isSkillPending(skill.id)}
										<div class="text-gray-400 dark:text-gray-500">
											<Spinner className="size-3" />
										</div>
									{/if}

									<button
										type="button"
										class="disabled:cursor-wait disabled:opacity-60"
										disabled={isSkillPending(skill.id)}
										on:click|stopPropagation|preventDefault
									>
										<Switch
											bind:state={skill.is_active}
											on:change={() => handleToggleSkill(skill)}
										/>
									</button>
								</div>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	{#if total > SKILLS_PER_PAGE}
		<Pagination bind:page count={total} perPage={SKILLS_PER_PAGE} />
	{/if}
</div>
