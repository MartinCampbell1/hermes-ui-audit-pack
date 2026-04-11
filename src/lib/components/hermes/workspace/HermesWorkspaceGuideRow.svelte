<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<any>('i18n');

	export let title = '';
	export let description = '';
	export let metaItems: string[] = [];

	$: visibleMetaItems = metaItems.filter(Boolean);
</script>

<div
	class="mx-2 mb-2 rounded-xl border border-gray-100/80 bg-gray-50/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/40"
>
	<div class="flex items-start justify-between gap-3">
		<div class="min-w-0">
			<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
				{title || $i18n.t('Workspace')}
			</div>
			{#if description}
				<div class="mt-0.5 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
					{description}
				</div>
			{/if}
		</div>

		{#if $$slots.actions}
			<div class="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
				<slot name="actions" />
			</div>
		{/if}
	</div>

	{#if visibleMetaItems.length > 0}
		<div class="mt-2 flex flex-wrap gap-1.5">
			{#each visibleMetaItems as item}
				<div
					class="max-w-full rounded-full bg-white/80 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-950/70 dark:text-gray-400"
				>
					<span class="block max-w-full truncate">{item}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
