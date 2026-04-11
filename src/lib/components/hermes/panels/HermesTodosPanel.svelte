<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext<any>('i18n');

	export let active = false;
	export let history = {};

	const taskLineRegex = /^[\s>*-]*[-*]\s+\[([ xX])\]\s+(.+)$/gm;

	const extractTodos = (messages: Record<string, any>): any[] => {
		if (!messages) return [];

		return (Object.values(messages) as any[]).flatMap((message: any) => {
			if (!message?.content || typeof message.content !== 'string') {
				return [];
			}

			const matches = Array.from(message.content.matchAll(taskLineRegex)) as RegExpMatchArray[];
			return matches.map((match: RegExpMatchArray, index) => ({
				id: `${message.id}-${index}`,
				checked: match[1].toLowerCase() === 'x',
				text: match[2].trim(),
				role: message.role
			}));
		});
	};

	let todoItems: any[] = [];
	let openCount = 0;

	$: todoItems = extractTodos((history as any)?.messages ?? {});
	$: openCount = todoItems.filter((item) => !item.checked).length;
</script>

<div class="flex h-full min-h-0 flex-col px-2 py-2">
	<div class="flex items-center justify-between gap-2 px-2 pb-2">
		<div>
			<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
				{$i18n.t('Action items')}
			</div>
			<div class="text-[11px] text-gray-400 dark:text-gray-500">
				{$i18n.t('{{COUNT}} open items', { COUNT: openCount })}
			</div>
		</div>
	</div>

	<div class="flex-1 min-h-0 overflow-y-auto px-1 pb-2">
		{#if todoItems.length === 0}
			<div class="px-3 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
				{$i18n.t('No action items found in this chat.')}
			</div>
		{:else}
			<div class="flex flex-col gap-1.5">
				{#each todoItems as item (item.id)}
					<div
						class="rounded-xl border border-gray-100/80 bg-white/80 px-3 py-2.5 dark:border-gray-800/80 dark:bg-gray-900/50"
					>
						<div class="flex items-start gap-2.5">
							<div class="mt-0.5 shrink-0">
								<div
									class="flex size-4 items-center justify-center rounded border border-gray-200 dark:border-gray-700"
								>
									{#if item.checked}
										<div class="size-2 rounded-sm bg-gray-700 dark:bg-gray-200"></div>
									{/if}
								</div>
							</div>

							<div class="min-w-0 flex-1">
								<div
									class="text-sm leading-6 {item.checked
										? 'text-gray-400 line-through dark:text-gray-500'
										: 'text-gray-800 dark:text-gray-100'}"
								>
									{item.text}
								</div>
								<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
									{$i18n.t(item.role === 'assistant' ? 'Captured from assistant' : 'Captured from user')}
								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
