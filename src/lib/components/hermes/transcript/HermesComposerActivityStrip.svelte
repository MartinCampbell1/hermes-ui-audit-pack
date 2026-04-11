<script lang="ts">
	import { getContext } from 'svelte';

	import StatusHistory from '$lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte';
	import CodeExecutions from '$lib/components/chat/Messages/CodeExecutions.svelte';
	import { getHermesVisibleStatusEntries } from '$lib/utils/hermesTranscript';

	const i18n = getContext<any>('i18n');

	const TOOL_PREVIEW_LIMIT = 2;

	export let message: any = null;
	export let statusUpdatesEnabled = true;

	$: statusEntries = getHermesVisibleStatusEntries(message);
	$: hasVisibleStatus =
		statusUpdatesEnabled && statusEntries.length > 0 && !(statusEntries.at(-1)?.hidden ?? false);
	$: allCodeExecutions = Array.isArray(message?.code_executions) ? message.code_executions : [];
	$: codeExecutions = allCodeExecutions.slice(-TOOL_PREVIEW_LIMIT);
	$: toolActivityCount = allCodeExecutions.length;
	$: showStrip = hasVisibleStatus || toolActivityCount > 0;
	$: title = !message?.done
		? $i18n.t('Running')
		: hasVisibleStatus && toolActivityCount > 0
			? $i18n.t('Agent activity')
			: hasVisibleStatus
				? $i18n.t('Status')
				: $i18n.t('Tools');
	$: activityMeta = [
		hasVisibleStatus
			? statusEntries.length === 1
				? $i18n.t('1 update')
				: $i18n.t('{{COUNT}} updates', { COUNT: statusEntries.length })
			: null,
		toolActivityCount > 0
			? toolActivityCount === 1
				? $i18n.t('1 tool')
				: $i18n.t('{{COUNT}} tools', { COUNT: toolActivityCount })
			: null
	]
		.filter(Boolean)
		.join(' • ');
</script>

{#if showStrip}
	<div
		class="rounded-xl border border-gray-100/80 bg-gray-50/80 px-2.5 py-2 dark:border-gray-800/80 dark:bg-gray-900/45"
	>
		<div class="flex items-center justify-between gap-2 px-0.5">
			<div
				class="min-w-0 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
			>
				{#if !message?.done}
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

				<span>{title}</span>
			</div>

			{#if activityMeta}
				<div
					class="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[11px] text-gray-400 dark:bg-gray-950/70 dark:text-gray-500"
				>
					{activityMeta}
				</div>
			{/if}
		</div>

		<div class="mt-1.5 flex flex-col gap-1.5">
			{#if hasVisibleStatus}
				<StatusHistory statusHistory={statusEntries} compact={true} />
			{/if}

			{#if codeExecutions.length > 0}
				<CodeExecutions codeExecutions={codeExecutions} compact={true} />
			{/if}
		</div>
	</div>
{/if}
