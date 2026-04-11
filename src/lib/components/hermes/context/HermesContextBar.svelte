<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';

	import type { HermesContextSummary, HermesScopeChip, HermesScopeTone } from '$lib/stores';
	import { getHermesModelSourceLabelKey } from '$lib/utils/hermesSessions';
	import HermesScopeBadge from './HermesScopeBadge.svelte';

	const i18n = getContext<any>('i18n');
	const dispatch = createEventDispatcher<{
		workspace: void;
		profile: void;
		session: void;
	}>();

	export let summary: HermesContextSummary | null = null;
	export let compact = false;

	const getModelTone = (source: HermesContextSummary['modelSource']): HermesScopeTone =>
		source === 'fallback' ? 'warning' : source === 'unknown' ? 'muted' : 'default';

	$: chips = summary
		? [
				summary.workspaceLabel
					? ({
							id: 'workspace',
							label: `${$i18n.t('Workspace')}: ${summary.workspaceLabel}`,
							scope: 'workspace',
							tone: 'muted',
							clickTarget: 'workspace'
						} satisfies HermesScopeChip)
					: null,
				summary.profileLabel
					? ({
							id: 'profile',
							label: `${$i18n.t('Hermes profile')}: ${summary.profileLabel}`,
							scope: 'profile',
							tone: 'default',
							clickTarget: 'profile'
						} satisfies HermesScopeChip)
					: null,
				summary.sessionStateLabel
					? ({
							id: 'session',
							label: `${$i18n.t('Session')}: ${$i18n.t(summary.sessionStateLabel)}`,
							scope: 'session',
							tone: 'default',
							clickTarget: 'session'
						} satisfies HermesScopeChip)
					: null,
				summary.activeModelLabel
					? ({
							id: 'model-source',
							label: `${$i18n.t('Model source')}: ${$i18n.t(
								getHermesModelSourceLabelKey(summary.modelSource)
							)}`,
							scope: summary.modelSource === 'fallback' ? 'fallback' : 'active',
							tone: getModelTone(summary.modelSource),
							clickTarget: 'session'
						} satisfies HermesScopeChip)
					: null,
				summary.activeModelLabel
					? ({
							id: 'model',
							label: `${$i18n.t('Model')}: ${summary.activeModelLabel}`,
							scope: 'active',
							tone: summary.modelSource === 'fallback' ? 'warning' : 'default',
							clickTarget: 'session'
						} satisfies HermesScopeChip)
					: null
			].filter(Boolean)
		: [];

	const handleChipClick = (chip: HermesScopeChip) => {
		if (chip.clickTarget === 'workspace') {
			dispatch('workspace');
			return;
		}

		if (chip.clickTarget === 'profile') {
			dispatch('profile');
			return;
		}

		dispatch('session');
	};
</script>

{#if chips.length > 0}
	<div class={`flex max-w-full items-center gap-1 overflow-x-auto scrollbar-hidden ${compact ? '' : 'mt-1'}`}>
		{#each chips as chip}
			<button type="button" class="shrink-0" on:click={() => handleChipClick(chip)}>
				<HermesScopeBadge
					label={chip.label}
					scope={chip.scope}
					tone={chip.tone ?? 'default'}
					clickable={true}
				/>
			</button>
		{/each}
	</div>
{/if}
