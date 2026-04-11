<script lang="ts">
	import type { HermesContextScope, HermesScopeTone } from '$lib/stores';

	export let label = '';
	export let scope: HermesContextScope = 'chat';
	export let tone: HermesScopeTone = 'default';
	export let clickable = false;

	const toneClasses: Record<HermesScopeTone, string> = {
		default: 'bg-gray-50/80 text-gray-600 dark:bg-gray-850/70 dark:text-gray-300',
		muted: 'bg-gray-50/60 text-gray-500 dark:bg-gray-900/60 dark:text-gray-400',
		success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
		warning: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
		danger: 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300'
	};
</script>

<div
	class={`inline-flex max-w-full items-center rounded-full px-2 py-0.5 text-[11px] ${toneClasses[tone]} ${
		clickable ? 'transition hover:opacity-90' : ''
	}`}
	data-scope={scope}
>
	<span class="truncate">{label}</span>
</div>
