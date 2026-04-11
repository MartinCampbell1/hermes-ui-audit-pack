<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext<any>('i18n');

	import StatusItem from './StatusHistory/StatusItem.svelte';

	export let statusHistory: any[] = [];
	export let expand = false;
	export let compact = false;

	let showHistory = true;

	$: if (expand) {
		showHistory = true;
	} else {
		showHistory = false;
	}

	let history: any[] = [];
	let status: any = null;

	$: if (history && history.length > 0) {
		status = history.at(-1) ?? null;
	}

	$: if (
		statusHistory.length !== history.length ||
		JSON.stringify(statusHistory) !== JSON.stringify(history)
	) {
		history = statusHistory;
	}
</script>

{#if history && history.length > 0}
	{#if status?.hidden !== true}
		<div class="text-sm flex flex-col w-full">
			<button
				class="w-full text-left {compact
					? 'rounded-lg border border-gray-100/80 bg-white/75 px-2.5 py-2 transition hover:bg-white dark:border-gray-800/80 dark:bg-gray-950/70 dark:hover:bg-gray-950'
					: ''}"
				aria-label={$i18n.t('Toggle status history')}
				aria-expanded={showHistory}
				on:click={() => {
					showHistory = !showHistory;
				}}
			>
				<div class="flex items-start justify-between gap-2">
					<div class="min-w-0 flex items-start gap-2">
						<StatusItem {status} {compact} />
					</div>

					{#if compact && history.length > 1}
						<div
							class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-900 dark:text-gray-400"
						>
							{history.length}
						</div>
					{/if}
				</div>
			</button>

			{#if showHistory}
				<div class="flex flex-row {compact ? 'mt-1 px-1' : ''}">
					{#if history.length > 1}
						<div class="w-full">
							{#each history as status, idx}
								<div class="flex items-stretch gap-2 mb-1">
									<div class=" ">
										<div class="pt-3 px-1 mb-1.5">
											<span class="relative flex size-1.5 rounded-full justify-center items-center">
												<span
													class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-400"
												></span>
											</span>
										</div>
										{#if idx !== history.length - 1}
											<div
												class="w-[0.5px] ml-[6.5px] h-[calc(100%-14px)] bg-gray-300 dark:bg-gray-700"
											></div>
										{/if}
									</div>

									<StatusItem {status} done={true} {compact} />
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
{/if}
