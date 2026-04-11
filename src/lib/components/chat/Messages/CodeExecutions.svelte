<script lang="ts">
	import { getContext } from 'svelte';

	import { chatControlsOpenTarget, showControls } from '$lib/stores';
	import CodeExecutionModal from './CodeExecutionModal.svelte';
	import HermesToolActivityRow from '$lib/components/hermes/transcript/HermesToolActivityRow.svelte';
	import { getHermesToolExecutionSurfaceSummary } from '$lib/utils/hermesTranscript';
	import { getValidHermesGeneratedFiles } from '$lib/utils/hermesWorkspace';

	const i18n = getContext<any>('i18n');

	export let codeExecutions: any[] = [];
	export let compact = false;

	let selectedCodeExecution: any = null;
	let showCodeExecutionModal = false;

	$: if (codeExecutions) {
		updateSelectedCodeExecution();
	}

	const updateSelectedCodeExecution = () => {
		if (selectedCodeExecution) {
			selectedCodeExecution =
				codeExecutions.find((execution) => execution.id === selectedCodeExecution?.id) ?? null;
		}
	};

	const getExecutionState = (execution: any) => {
		if (!execution?.result) {
			return 'running';
		}

		if (execution.result?.error) {
			return 'failed';
		}

		return 'done';
	};

	const getExecutionScopeLabel = (execution: any) =>
		getGeneratedFileCount(execution) > 0 ? $i18n.t('Generated in this chat') : '';

	const getGeneratedFiles = (execution: any) =>
		getValidHermesGeneratedFiles(execution?.result?.files);

	const getGeneratedFileCount = (execution: any) => getGeneratedFiles(execution).length;

	const openWorkspace = () => {
		chatControlsOpenTarget.set('workspace');
		showControls.set(true);
	};
</script>

<CodeExecutionModal
	bind:show={showCodeExecutionModal}
	codeExecution={selectedCodeExecution as any}
/>

{#if codeExecutions.length > 0}
	<div class="w-full flex flex-col gap-1 {compact ? '' : 'mt-1 mb-2'}">
		{#each codeExecutions as execution (execution.id)}
			{@const executionSummary = getHermesToolExecutionSurfaceSummary(
				execution,
				$i18n.t('Completed')
			)}
			<HermesToolActivityRow
				name={execution.name}
				summary={executionSummary.summary}
				meta={executionSummary.meta}
				scopeLabel={getExecutionScopeLabel(execution)}
				state={getExecutionState(execution)}
				actionLabel={getGeneratedFileCount(execution) > 0 ? $i18n.t('Open workspace') : ''}
				actionAriaLabel={$i18n.t('Open generated files in workspace')}
				onClick={() => {
					selectedCodeExecution = execution;
					showCodeExecutionModal = true;
				}}
				onActionClick={openWorkspace}
			/>
		{/each}
	</div>
{/if}
