<script lang="ts">
	import { getContext } from 'svelte';
	import { chatControlsOpenTarget, showControls } from '$lib/stores';
	import CodeBlock from './CodeBlock.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { getValidHermesGeneratedFiles } from '$lib/utils/hermesWorkspace';
	const i18n = getContext('i18n');

	export let show = false;
	export let codeExecution = null;

	$: generatedFiles = getValidHermesGeneratedFiles(codeExecution?.result?.files);
	$: hasGeneratedFiles = generatedFiles.length > 0;

	const openWorkspace = () => {
		chatControlsOpenTarget.set('workspace');
		showControls.set(true);
		show = false;
		codeExecution = null;
	};
</script>

<Modal size="lg" bind:show>
	<div>
		<div class="flex justify-between dark:text-gray-300 px-5 pt-4 pb-2">
			<div class="text-lg font-medium self-center flex flex-col gap-0.5 capitalize">
				{#if codeExecution?.result}
					<div>
						{#if codeExecution.result?.error}
							<Badge type="error" content="error" />
						{:else if codeExecution.result?.output}
							<Badge type="success" content="success" />
						{:else}
							<Badge type="warning" content="incomplete" />
						{/if}
					</div>
				{/if}

				<div class="flex gap-2 items-center">
					{#if !codeExecution?.result}
						<div>
							<Spinner className="size-4" />
						</div>
					{/if}

					<div>
						{#if codeExecution?.name}
							{$i18n.t('Code execution')}: {codeExecution?.name}
						{:else}
							{$i18n.t('Code execution')}
						{/if}
					</div>
				</div>
			</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
					codeExecution = null;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-4 pb-5">
			<div
				class="flex flex-col w-full dark:text-gray-200 overflow-y-scroll max-h-[22rem] scrollbar-hidden"
			>
				<div class="flex flex-col w-full">
					<CodeBlock
						id="code-exec-{codeExecution?.id}-code"
						lang={codeExecution?.language ?? ''}
						code={codeExecution?.code ?? ''}
						className=""
						editorClassName={codeExecution?.result &&
						(codeExecution?.result?.error || codeExecution?.result?.output)
							? 'rounded-b-none'
							: ''}
						run={false}
					/>
				</div>

				{#if codeExecution?.result && (codeExecution?.result?.error || codeExecution?.result?.output)}
					<div class="dark:bg-[#202123] dark:text-white px-4 py-4 rounded-b-lg flex flex-col gap-3">
						{#if codeExecution?.result?.error}
							<div>
								<div class=" text-gray-500 text-xs mb-1">{$i18n.t('ERROR')}</div>
								<div class="text-sm">{codeExecution?.result?.error}</div>
							</div>
						{/if}
						{#if codeExecution?.result?.output}
							<div>
								<div class=" text-gray-500 text-xs mb-1">{$i18n.t('OUTPUT')}</div>
								<div class="text-sm">{codeExecution?.result?.output}</div>
							</div>
						{/if}
					</div>
				{/if}
				{#if hasGeneratedFiles}
					<div class="flex flex-col w-full">
						<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />
						<div class="flex items-center justify-between gap-2">
							<div class="text-sm font-medium dark:text-gray-300">
								{$i18n.t('Files')}
							</div>
							<button
								type="button"
								class="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
								aria-label={$i18n.t('Open generated files in workspace')}
								on:click={openWorkspace}
							>
								{$i18n.t('Open workspace')}
							</button>
						</div>
						<ul class="mt-1 list-disc pl-4 text-xs">
							{#each generatedFiles as file}
								<li>
									<a href={file.url} target="_blank" rel="noreferrer">{file.name}</a>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</div>
		</div>
	</div>
</Modal>
