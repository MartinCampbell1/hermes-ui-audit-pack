<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<any>('i18n');

	export let label = '';
	export let title = '';
	export let subtitle = '';
	export let badge = '';
	export let metaItems: string[] = [];
	export let stats: Array<{ label: string; value: string | number }> = [];

	$: visibleMetaItems = metaItems.filter(Boolean);
	$: visibleStats = stats.filter((stat) => stat && `${stat.value}`.length > 0);
</script>

<div class="border-b border-gray-100 px-3 pt-2.5 pb-2 dark:border-gray-800">
	<div class="flex items-start justify-between gap-2">
		<div class="min-w-0">
			<div
				class="text-[11px] font-medium uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
			>
				{label || $i18n.t('Workspace')}
			</div>
			<div class="mt-0.5 line-clamp-1 text-sm font-medium text-gray-900 dark:text-gray-100">
				{title || $i18n.t('Workspace')}
			</div>
		</div>

		{#if badge}
			<div
				class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300"
			>
				{badge}
			</div>
		{/if}
	</div>

	{#if subtitle}
		<div class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">{subtitle}</div>
	{/if}

	{#if visibleMetaItems.length > 0}
		<div class="mt-2 flex flex-wrap gap-1.5">
			{#each visibleMetaItems as item}
				<div
					class="max-w-full rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
				>
					<span class="block max-w-full truncate">{item}</span>
				</div>
			{/each}
		</div>
	{/if}

	{#if visibleStats.length > 0}
		<div class="mt-3 grid grid-cols-3 gap-2">
			{#each visibleStats as stat}
				<div class="rounded-xl bg-gray-50 px-2.5 py-2 dark:bg-gray-950/70">
					<div class="text-[10px] uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
						{stat.label}
					</div>
					<div class="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">
						{stat.value}
					</div>
				</div>
			{/each}
		</div>
	{/if}

	{#if $$slots.actions}
		<div class="mt-2 flex flex-wrap gap-1.5">
			<slot name="actions" />
		</div>
	{/if}
</div>
