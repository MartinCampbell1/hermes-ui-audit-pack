<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		switchHermesProfile,
		type HermesProfile,
		type HermesProfileSwitchResponse
	} from '$lib/apis/hermes';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import {
		hermesProfilesLoaded,
		hermesProfilesLoading,
		hermesProfilesStore,
		settings,
		showSettings,
		user
	} from '$lib/stores';
	import { ensureHermesContextBundle } from '$lib/utils/hermesContext';

	const i18n = getContext<any>('i18n');

	// TODO(21st): Replace this stopgap local panel pattern with a 21st.dev-derived micro-surface once MCP auth is fixed.

	export let active = false;
	export let taskIds: string[] | null = null;
	export let hermesStreamActive = false;
	export let onProfileSwitched: (
		payload: HermesProfileSwitchResponse
	) => void | Promise<void> = () => {};

	let profileLoadError = '';
	let inspectedProfileName: string | null = null;
	let switchingProfileName: string | null = null;
	let showAdvancedDetails = false;

	$: profileMeta = [$user?.role ? $i18n.t($user.role === 'admin' ? 'Admin' : 'User') : ''].filter(
		Boolean
	);
	$: defaultModelLabel = $settings?.models?.[0] ?? $i18n.t('Not set');
	$: hermesProfiles = $hermesProfilesStore?.items ?? [];
	$: activeHermesProfile =
		(hermesProfiles.find((profile) => profile.is_active) as HermesProfile | undefined) ??
		hermesProfiles[0] ??
		null;

	const getHermesProfileScopeChips = (profile: HermesProfile | null) =>
		profile
			? [
					profile.is_active
						? $i18n.t('Inherited Hermes profile')
						: $i18n.t('Available Hermes profile'),
					profile.memory_enabled || profile.has_memory
						? $i18n.t('Profile memory enabled')
						: '',
					profile.user_profile_enabled || profile.has_user_profile
						? $i18n.t('User profile enabled')
						: '',
					profile.skill_count > 0
						? $i18n.t('Profile skills: {{COUNT}}', { COUNT: profile.skill_count })
						: ''
				].filter(Boolean)
			: [];

	const getHermesProfileAdvancedChips = (profile: HermesProfile | null) =>
		profile
			? [
					profile.model,
					profile.provider,
					profile.has_env ? $i18n.t('Environment') : '',
					profile.has_soul ? $i18n.t('Soul') : '',
					profile.gateway_running ? $i18n.t('Gateway running') : ''
				].filter(Boolean)
			: [];

	const getHermesProfileMetaLine = (profile: HermesProfile | null) =>
		[profile?.model, profile?.provider].filter(Boolean).join(' · ');

	$: hermesProfileChips = getHermesProfileScopeChips(activeHermesProfile);
	$: hermesProfileAdvancedChips = getHermesProfileAdvancedChips(activeHermesProfile);
	$: profileSourceOfTruthItems = [
		`${$i18n.t('Active model')}: ${activeHermesProfile?.model ?? $i18n.t('Not set')}`,
		`${$i18n.t('Browser fallback')}: ${defaultModelLabel}`
	];
	$: if (hermesProfiles.length > 0) {
		const hasSelectedProfile =
			inspectedProfileName !== null &&
			hermesProfiles.some((profile) => profile.name === inspectedProfileName);

		if (!hasSelectedProfile) {
			inspectedProfileName = activeHermesProfile?.name ?? hermesProfiles[0].name;
		}
	}
	$: inspectedHermesProfile =
		(hermesProfiles.find((profile) => profile.name === inspectedProfileName) as
			| HermesProfile
			| undefined) ?? null;
	$: inspectedProfileChips = getHermesProfileScopeChips(inspectedHermesProfile);
	$: inspectedProfileAdvancedChips = getHermesProfileAdvancedChips(inspectedHermesProfile);
	$: hasActiveTasks = (taskIds?.length ?? 0) > 0;
	$: hasActiveWork = hasActiveTasks || hermesStreamActive;

	const getErrorMessage = (error: any, fallback: string) => {
		if (typeof error === 'string') {
			return error;
		}

		return error?.detail ?? error?.message ?? fallback;
	};

	const loadProfiles = async (force = false) => {
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

	const handleSwitchProfile = async (profile: HermesProfile) => {
		if (!profile || profile.is_active || switchingProfileName || hasActiveWork) {
			return;
		}

		switchingProfileName = profile.name;
		profileLoadError = '';

		try {
			const nextProfiles = await switchHermesProfile(localStorage.token, profile.name);
			hermesProfilesStore.set(nextProfiles);
			hermesProfilesLoaded.set(true);
			inspectedProfileName = nextProfiles.active_profile;
			await onProfileSwitched(nextProfiles);
			toast.success($i18n.t('Switched Hermes profile.'));
		} catch (error) {
			console.error(error);
			toast.error(getErrorMessage(error, $i18n.t('Failed to switch Hermes profile.')));
		} finally {
			switchingProfileName = null;
		}
	};

	$: if (active && !$hermesProfilesLoaded && !$hermesProfilesLoading) {
		loadProfiles();
	}
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	<div
		class="rounded-xl border border-gray-100/80 bg-white/80 px-4 py-4 dark:border-gray-800/80 dark:bg-gray-900/50"
	>
		<div class="flex items-center gap-3">
			<img
				src={$user?.profile_image_url || '/user.png'}
				alt={$i18n.t('Profile')}
				class="size-10 rounded-full object-cover"
			/>

			<div class="min-w-0">
				<div class="line-clamp-1 text-sm font-medium text-gray-800 dark:text-gray-100">
					{$user?.name ?? $i18n.t('User')}
				</div>
				<div class="line-clamp-1 text-xs text-gray-500 dark:text-gray-400">
					{$user?.email}
				</div>
			</div>
		</div>

		{#if profileMeta.length > 0}
			<div class="mt-3 flex flex-wrap gap-1.5">
				{#each profileMeta as item}
					<div
						class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
					>
						{item}
					</div>
				{/each}
			</div>
		{/if}

			<div class="mt-3 text-xs leading-5 text-gray-500 dark:text-gray-400">
				{$i18n.t(
					'Browser identity is shown here. The active Hermes profile below is the source of truth for this run; fallback model details stay in the sections below.'
				)}
			</div>
		</div>

	<div
		class="mt-2 rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
	>
		<div class="flex items-start justify-between gap-3">
			<div class="min-w-0">
					<div
						class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
					>
						{$i18n.t('Active Hermes profile')}
					</div>
					<div class="mt-2 line-clamp-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{activeHermesProfile?.name ?? $hermesProfilesStore?.active_profile ?? $i18n.t('Not set')}
					</div>
					<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
						{$i18n.t('Source of truth for the current Hermes run.')}
					</div>
				</div>

			{#if $hermesProfilesLoading}
				<div class="mt-0.5 text-gray-400">
					<Spinner className="size-4" />
				</div>
			{:else if activeHermesProfile?.is_active}
				<div
					class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400"
					>
						{$i18n.t('In use')}
					</div>
				{/if}
			</div>

			<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
				{$i18n.t('Inherited Hermes context from the active profile.')}
			</div>

		{#if profileLoadError}
			<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">{profileLoadError}</div>
		{:else if activeHermesProfile}
			{#if hasActiveWork}
				<div class="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
					{$i18n.t('Finish the current Hermes response before switching profiles.')}
				</div>
			{/if}

			{#if hermesProfileChips.length > 0}
				<div class="mt-2 flex flex-wrap gap-1.5">
					{#each hermesProfileChips as item}
						<div
							class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
						>
							{item}
						</div>
					{/each}
				</div>
			{/if}

			<div class="mt-2 flex flex-wrap gap-1.5">
				{#each profileSourceOfTruthItems as item}
					<div
						class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
					>
						{item}
					</div>
				{/each}
			</div>

			<div class="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
				{$i18n.t('Hermes profile decides the active model here. The Open WebUI selector is only a browser fallback.')}
			</div>

			<div class="mt-3 border-t border-gray-100/80 pt-3 dark:border-gray-800/80">
				<button
					type="button"
					class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
					on:click={() => {
						showAdvancedDetails = !showAdvancedDetails;
					}}
				>
					{$i18n.t(showAdvancedDetails ? 'Hide details' : 'Advanced details')}
				</button>

				{#if showAdvancedDetails}
					<div class="mt-3 truncate text-[11px] text-gray-500 dark:text-gray-400">
						{$i18n.t('Home directory')}: {activeHermesProfile.path}
					</div>

					{#if hermesProfileAdvancedChips.length > 0}
						<div class="mt-2 flex flex-wrap gap-1.5">
							{#each hermesProfileAdvancedChips as item}
								<div
									class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
								>
									{item}
								</div>
							{/each}
						</div>
					{/if}

					<div class="mt-3 flex flex-wrap gap-1.5">
						<button
							type="button"
							class="rounded-full bg-gray-900 px-2.5 py-1 text-[11px] font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
							on:click={() => showSettings.set(true)}
						>
							{$i18n.t('Open profile settings')}
						</button>

						<button
							type="button"
							class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
							on:click={() => showSettings.set(true)}
						>
							{$i18n.t('Personalization')}
						</button>
					</div>
				{/if}
			</div>

			{#if hermesProfiles.length > 1}
				<div class="mt-3 border-t border-gray-100/80 pt-3 dark:border-gray-800/80">
						<div
							class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
						>
							{$i18n.t('Available profiles')}
						</div>
						<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
							{$i18n.t('Inspect inherited Hermes defaults or switch the active profile.')}
						</div>

					<div class="mt-2 flex flex-col gap-1.5">
						{#each hermesProfiles as profile}
							<button
								type="button"
								class="w-full rounded-lg border px-2.5 py-2 text-left transition {profile.name ===
								inspectedProfileName
									? 'border-gray-200 bg-gray-50/80 dark:border-gray-700 dark:bg-gray-800/60'
									: 'border-gray-100/80 bg-white/40 hover:bg-gray-50/70 dark:border-gray-800/80 dark:bg-gray-900/30 dark:hover:bg-gray-800/40'}"
								on:click={() => {
									inspectedProfileName = profile.name;
								}}
							>
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0">
										<div class="line-clamp-1 text-xs font-medium text-gray-700 dark:text-gray-200">
											{profile.name}
										</div>
										{#if getHermesProfileMetaLine(profile)}
											<div class="mt-0.5 line-clamp-1 text-[11px] text-gray-400 dark:text-gray-500">
												{getHermesProfileMetaLine(profile)}
											</div>
										{/if}
									</div>

									<div class="flex shrink-0 flex-wrap justify-end gap-1">
										{#if profile.is_active}
											<div
												class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-300"
											>
												{$i18n.t('In use')}
											</div>
										{/if}
										{#if profile.is_default}
											<div
												class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-700 dark:text-gray-300"
											>
												{$i18n.t('Browser fallback default')}
											</div>
										{/if}
									</div>
								</div>

								{#if profile.name === inspectedProfileName}
									<div class="mt-2 border-t border-gray-100/80 pt-2 dark:border-gray-700/80">
										{#if inspectedProfileChips.length > 0}
											<div class="flex flex-wrap gap-1.5">
												{#each inspectedProfileChips as item}
													<div
														class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-700 dark:text-gray-300"
													>
														{item}
													</div>
												{/each}
											</div>
										{/if}

										{#if showAdvancedDetails}
											<div class="mt-2 truncate text-[11px] text-gray-500 dark:text-gray-400">
												{$i18n.t('Home directory')}: {profile.path}
											</div>

											{#if inspectedProfileAdvancedChips.length > 0}
												<div class="mt-2 flex flex-wrap gap-1.5">
													{#each inspectedProfileAdvancedChips as item}
														<div
															class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-700 dark:text-gray-300"
														>
															{item}
														</div>
													{/each}
												</div>
											{/if}
										{/if}
									</div>
								{/if}
							</button>
						{/each}
					</div>

					{#if inspectedHermesProfile && !inspectedHermesProfile.is_active}
						<div class="mt-3">
							<button
								type="button"
								class="rounded-full bg-gray-900 px-2.5 py-1 text-[11px] font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
								disabled={switchingProfileName !== null || hasActiveWork}
								on:click={() => handleSwitchProfile(inspectedHermesProfile)}
							>
								{switchingProfileName === inspectedHermesProfile.name
									? `${$i18n.t('Switching')}...`
									: $i18n.t('Use profile')}
							</button>

							{#if hasActiveWork}
								<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
									{$i18n.t('Cannot switch profiles while Hermes is still busy.')}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
		{:else if $hermesProfilesLoaded}
			<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('Profile context unavailable.')}
			</div>
		{/if}
	</div>

	{#if showAdvancedDetails}
		<div class="mt-2 flex flex-col gap-1.5 px-1 pb-2">
			<div
				class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
			>
					<div
						class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
					>
						{$i18n.t('Browser fallback model')}
					</div>
					<div class="mt-2 text-sm text-gray-700 dark:text-gray-200">{defaultModelLabel}</div>
					<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
						{$i18n.t('Open WebUI fallback only; Hermes uses the active profile model above.')}
					</div>
				</div>
			</div>
	{/if}
</div>
