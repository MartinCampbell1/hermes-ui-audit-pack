<script lang="ts">
	import dayjs from 'dayjs';
	import { getContext } from 'svelte';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import HermesToolActivityRow from '$lib/components/hermes/transcript/HermesToolActivityRow.svelte';
	import { formatDate } from '$lib/utils';
	import {
		getHermesImportedToolContent,
		getHermesImportedToolName,
		getHermesImportedToolSurfaceSummary
	} from '$lib/utils/hermesTranscript';

	const i18n = getContext<any>('i18n');

	export let history: any = {};
	export let messageId = '';

	let expanded = false;

	$: message = history?.messages?.[messageId] ?? null;
	$: toolName = getHermesImportedToolName(message);
	$: detailContent = getHermesImportedToolContent(message);
	$: surfaceSummary = getHermesImportedToolSurfaceSummary(message, $i18n.t('Completed'));
	$: toolMeta = surfaceSummary.meta;
	$: detailsLabel = expanded ? $i18n.t('Hide') : $i18n.t('Details');

	const toggleExpanded = () => {
		if (!detailContent) {
			return;
		}

		expanded = !expanded;
	};
</script>

{#if message}
	<div
		class="w-full rounded-xl border border-gray-100/80 bg-gray-50/80 px-3 py-2 dark:border-gray-800/80 dark:bg-gray-900/45"
	>
		<div class="mb-1.5 flex items-center justify-between gap-2 px-0.5">
			<div
				class="min-w-0 text-[11px] font-medium uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
			>
				{$i18n.t('Tool')}
			</div>

			{#if message.timestamp}
				<div
					class="shrink-0 text-xs font-medium first-letter:capitalize text-gray-400 transition group-hover:visible dark:text-gray-500"
				>
					<Tooltip content={dayjs(message.timestamp * 1000).format('LLLL')}>
						<span class="line-clamp-1"
							>{$i18n.t(formatDate(message.timestamp * 1000), {
								LOCALIZED_TIME: dayjs(message.timestamp * 1000).format('LT'),
								LOCALIZED_DATE: dayjs(message.timestamp * 1000).format('L')
							})}</span
						>
					</Tooltip>
				</div>
			{/if}
		</div>

		<HermesToolActivityRow
			name={toolName}
			summary={surfaceSummary.summary}
			meta={toolMeta}
			scopeLabel={$i18n.t('Imported tool result')}
			state="done"
			actionLabel={detailContent ? detailsLabel : ''}
			actionAriaLabel={detailContent ? detailsLabel : ''}
			onClick={toggleExpanded}
			onActionClick={toggleExpanded}
		/>

		{#if expanded && detailContent}
			<div
				class="mt-1.5 rounded-lg bg-white/85 px-3 py-2 text-xs text-gray-600 dark:bg-gray-950/70 dark:text-gray-300"
			>
				<pre class="whitespace-pre-wrap break-words font-mono">{detailContent}</pre>
			</div>
		{/if}
	</div>
{/if}
