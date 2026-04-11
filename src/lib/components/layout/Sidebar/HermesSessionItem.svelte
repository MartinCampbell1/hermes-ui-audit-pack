<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';

	import {
		getHermesSessionActivityLabel,
		formatHermesSessionSourceLine,
		type HermesSessionListItem
	} from '$lib/utils/hermesSessions';

	const i18n = getContext<any>('i18n');
	const dispatch = createEventDispatcher<{
		open: HermesSessionListItem;
		import: HermesSessionListItem;
		hover: HermesSessionListItem;
	}>();

	export let session: HermesSessionListItem;
	export let busy = false;
	export let selected = false;
	export let showPreview = false;
	export let className = '';

	let mouseOver = false;

	$: activityLabel = getHermesSessionActivityLabel(session.updated_at);
	$: activityText = $i18n.t(activityLabel.key, activityLabel.values ?? {});
	$: sourceLine = formatHermesSessionSourceLine(session);
	$: showSecondaryDetails = showPreview || selected || mouseOver;
	$: showActionLabel = busy || selected || mouseOver;
	$: sessionStateLabel = session.imported_chat_id ? $i18n.t('Imported') : $i18n.t('Ready to import');
	$: actionLabel = busy
		? session.imported_chat_id
			? `${$i18n.t('Opening')}...`
			: `${$i18n.t('Importing')}...`
		: session.imported_chat_id
			? $i18n.t('Open chat')
			: $i18n.t('Import and open');

	const handleActivate = () => {
		if (busy) {
			return;
		}

		if (session.imported_chat_id) {
			dispatch('open', session);
			return;
		}

		dispatch('import', session);
	};

	const handleHover = () => {
		mouseOver = true;
		dispatch('hover', session);
	};
</script>

<button
	type="button"
	class="group flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left transition hover:bg-gray-50 dark:hover:bg-gray-900/70 {selected ? 'bg-gray-50 dark:bg-gray-850' : ''} {className}"
	on:click={handleActivate}
	on:mouseenter={handleHover}
	on:mouseleave={() => {
		mouseOver = false;
	}}
	on:focus={handleHover}
	on:blur={() => {
		mouseOver = false;
	}}
	disabled={busy}
	aria-label={`${session.title}. ${actionLabel}`}
	data-arrow-selected={selected ? 'true' : undefined}
>
	<div
		class="mt-1 size-2.5 shrink-0 rounded-full bg-gray-300 transition group-hover:bg-gray-400 dark:bg-gray-700 dark:group-hover:bg-gray-500"
	></div>

	<div class="min-w-0 flex-1">
		<div class="flex items-center gap-2">
			<div class="line-clamp-1 text-sm font-medium text-gray-800 dark:text-gray-100">
				{session.title}
			</div>

			{#if session.imported_chat_id}
				<div
					class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
				>
					{sessionStateLabel}
				</div>
			{/if}

			{#if session.imported_chat_archived}
				<div
					class="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
				>
					{$i18n.t('Archived')}
				</div>
			{/if}
		</div>

		{#if showSecondaryDetails}
			<div class="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
				{sessionStateLabel} · {activityText} · {session.message_count}
				{$i18n.t('Messages')}
			</div>

			{#if session.last_user_content}
				<div class="mt-0.5 line-clamp-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
					{session.last_user_content}
				</div>
			{/if}

			{#if sourceLine}
				<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{sourceLine}</div>
			{/if}
		{/if}
	</div>

	{#if showActionLabel}
		<div class="shrink-0 pt-0.5 text-[11px] font-medium text-gray-500 dark:text-gray-400">
			{actionLabel}
		</div>
	{/if}
</button>
