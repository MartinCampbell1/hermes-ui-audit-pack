<script lang="ts">
	import { getContext } from 'svelte';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';

	const i18n = getContext<any>('i18n');

	type ToolState = 'running' | 'done' | 'failed' | 'idle';

	export let name = '';
	export let summary = '';
	export let meta = '';
	export let scopeLabel = '';
	export let state: ToolState = 'idle';
	export let onClick: () => void = () => {};
	export let actionLabel = '';
	export let actionAriaLabel = '';
	export let onActionClick: () => void = () => {};

	$: stateLabel =
		state === 'running'
			? $i18n.t('Running')
			: state === 'failed'
				? $i18n.t('Failed')
				: '';
</script>

<div
	class="flex w-full items-center gap-2 rounded-lg bg-white/75 transition hover:bg-white dark:bg-gray-950/70 dark:hover:bg-gray-950"
>
	<button
		type="button"
		class="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-left"
		on:click={onClick}
	>
		<div
			class="flex size-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-300"
		>
			{#if state === 'running'}
				<Spinner className="size-3" />
			{:else if state === 'failed'}
				<XMark className="size-3" />
			{:else if state === 'done'}
				<Check strokeWidth="3" className="size-3" />
			{:else}
				<EllipsisHorizontal className="size-3" />
			{/if}
		</div>

		<div class="min-w-0 flex-1">
			<div class="line-clamp-1 text-sm font-medium text-gray-700 dark:text-gray-200">{name}</div>
			{#if summary}
				<div class="line-clamp-1 text-[11px] text-gray-500 dark:text-gray-400">{summary}</div>
			{/if}
			{#if meta || scopeLabel}
				<div class="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-gray-400 dark:text-gray-500">
					{#if meta}
						<div class="line-clamp-1">{meta}</div>
					{/if}
					{#if scopeLabel}
						<div class="line-clamp-1">{scopeLabel}</div>
					{/if}
				</div>
			{/if}
		</div>

		{#if stateLabel}
			<div class="shrink-0 text-[11px] text-gray-400 dark:text-gray-500">{stateLabel}</div>
		{/if}
	</button>

	{#if actionLabel}
		<button
			type="button"
			class="mr-2 shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 transition hover:bg-gray-200 hover:text-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
			aria-label={actionAriaLabel || actionLabel}
			on:click={onActionClick}
		>
			{actionLabel}
		</button>
	{/if}
</div>
