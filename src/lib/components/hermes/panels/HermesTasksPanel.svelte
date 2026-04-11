<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<any>('i18n');

	export let active = false;
	export let taskIds: string[] | null = null;
	export let stopResponse: Function = async () => {};

	$: visibleTaskIds = taskIds ?? [];
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	<div class="flex items-center justify-between gap-2 px-2 pb-2">
		<div>
			<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
				{$i18n.t('Running tasks')}
			</div>
			<div class="text-[11px] text-gray-400 dark:text-gray-500">
				{$i18n.t('Active in this chat')} · {visibleTaskIds.length}
			</div>
		</div>

		{#if visibleTaskIds.length > 0}
			<button
				type="button"
				class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
				on:click={async () => {
					await stopResponse();
				}}
			>
				{$i18n.t('Stop generation')}
			</button>
		{/if}
	</div>

	<div class="flex-1 min-h-0 overflow-y-auto px-1 pb-2">
		{#if visibleTaskIds.length === 0}
			<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('No running tasks in this chat.')}
			</div>
		{:else}
			<div class="flex flex-col gap-1.5">
				{#each visibleTaskIds as taskId}
					<div
						class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
					>
						<div class="flex items-center justify-between gap-3">
							<div class="min-w-0">
								<div
									class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500"
								>
									{$i18n.t('Task reference')}
								</div>
								<div class="mt-1 line-clamp-1 font-mono text-xs text-gray-700 dark:text-gray-200">
									{taskId}
								</div>
							</div>

							<div
								class="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
							>
								{$i18n.t('Active')}
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
