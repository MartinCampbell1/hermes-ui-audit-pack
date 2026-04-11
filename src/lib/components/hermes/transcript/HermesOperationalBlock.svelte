<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<any>('i18n');

	// TODO(21st): Replace this local operational grouping pattern with a 21st.dev-derived pattern once MCP auth is fixed.

	export let title = '';
	export let meta = '';
	export let busy = false;
</script>

<div
	class="mt-2.5 mb-1.5 w-full rounded-xl border border-gray-100/80 bg-gray-50/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
>
	<div class="flex items-center justify-between gap-2">
		<div
			class="min-w-0 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
		>
			{#if busy}
				<span class="relative flex size-2 shrink-0">
					<span
						class="absolute inline-flex h-full w-full animate-ping rounded-full bg-gray-400/50 dark:bg-gray-500/40"
					></span>
					<span class="relative inline-flex size-2 rounded-full bg-gray-400 dark:bg-gray-500"
					></span>
				</span>
			{:else}
				<span class="inline-flex size-2 shrink-0 rounded-full bg-gray-300 dark:bg-gray-600"></span>
			{/if}

			<span>{title || $i18n.t('Agent activity')}</span>
		</div>

		{#if meta}
			<div
				class="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[11px] text-gray-400 dark:bg-gray-950/70 dark:text-gray-500"
			>
				{meta}
			</div>
		{/if}
	</div>

	<div class="mt-2 flex flex-col gap-2">
		<slot />
	</div>
</div>
