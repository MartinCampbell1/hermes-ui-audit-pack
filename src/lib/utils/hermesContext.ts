import { get } from 'svelte/store';

import {
	getHermesProfiles,
	getHermesRuntime,
	getHermesWorkspaces,
	type HermesProfile,
	type HermesProfilesResponse,
	type HermesRuntime,
	type HermesWorkspacesResponse
} from '$lib/apis/hermes';
import {
	hermesContextLoaded,
	hermesContextLoading,
	hermesProfilesLoaded,
	hermesProfilesLoading,
	hermesProfilesStore,
	hermesRuntimeStore,
	hermesWorkspacesStore,
	type HermesContextSummary,
	type WorkspacePanelStatus
} from '$lib/stores';
import {
	getHermesSessionStateLabelKey,
	getResolvedHermesSessionContext
} from '$lib/utils/hermesSessions';

let pendingContextPromise: Promise<void> | null = null;
let pendingProfilesPromise: Promise<void> | null = null;

export const formatWorkspaceNameFromPath = (path: string | null | undefined) => {
	if (!path) {
		return '';
	}

	const normalized = path.replace(/\/+$/, '');

	if (!normalized) {
		return path;
	}

	return normalized.split('/').pop() ?? normalized;
};

export const getActiveHermesProfile = (profiles: HermesProfilesResponse | null): HermesProfile | null =>
	(profiles?.items?.find((item) => item.is_active) as HermesProfile | undefined) ??
	profiles?.items?.[0] ??
	null;

export const ensureHermesContextBundle = async (
	token: string,
	{ force = false, includeProfiles = false }: { force?: boolean; includeProfiles?: boolean } = {}
) => {
	if (!token) {
		hermesContextLoaded.set(true);
		if (includeProfiles) {
			hermesProfilesLoaded.set(true);
		}
		return;
	}

	if (!force && get(hermesContextLoaded) && (!includeProfiles || get(hermesProfilesLoaded))) {
		return;
	}

	if (!pendingContextPromise || force) {
		hermesContextLoading.set(true);

		const request = (async () => {
			const [runtime, workspaces] = await Promise.all([
				getHermesRuntime(token).catch(() => null),
				getHermesWorkspaces(token).catch(() => null)
			]);

			hermesRuntimeStore.set(runtime);
			hermesWorkspacesStore.set(workspaces);
			hermesContextLoaded.set(true);
		})()
			.finally(() => {
				hermesContextLoading.set(false);
				if (pendingContextPromise === request) {
					pendingContextPromise = null;
				}
			});

		pendingContextPromise = request;
	}

	await pendingContextPromise;

	if (includeProfiles && (!get(hermesProfilesLoaded) || force)) {
		if (!pendingProfilesPromise || force) {
			hermesProfilesLoading.set(true);

			const request = getHermesProfiles(token)
				.catch(() => null)
				.then((profiles) => {
					hermesProfilesStore.set(profiles);
					hermesProfilesLoaded.set(true);
				})
				.finally(() => {
					hermesProfilesLoading.set(false);
					if (pendingProfilesPromise === request) {
						pendingProfilesPromise = null;
					}
				});

			pendingProfilesPromise = request;
		}

		await pendingProfilesPromise;
	}
};

export const buildHermesContextSummary = ({
	chatHermesSession = null,
	chatMeta = null,
	runtime = null,
	workspaces = null,
	profiles = null,
	workspaceStatus = null,
	temporaryChatEnabled = false,
	currentMessageId = null,
	selectedModelLabel = '',
	generatedFileCount = 0,
	chatAttachedFileCount = 0,
	taskCount = 0
}: {
	chatHermesSession?: Record<string, any> | null;
	chatMeta?: Record<string, any> | null;
	runtime?: HermesRuntime | null;
	workspaces?: HermesWorkspacesResponse | null;
	profiles?: HermesProfilesResponse | null;
	workspaceStatus?: WorkspacePanelStatus | null;
	temporaryChatEnabled?: boolean;
	currentMessageId?: string | null;
	selectedModelLabel?: string;
	generatedFileCount?: number;
	chatAttachedFileCount?: number;
	taskCount?: number;
}): HermesContextSummary => {
	const currentHermesMeta = getResolvedHermesSessionContext({
		session: chatHermesSession,
		meta: chatMeta,
		runtime
	});
	const activeWorkspaceItem = workspaces?.items?.find((item) => item.is_active) ?? null;
	const activeProfile = getActiveHermesProfile(profiles);

	const activeModelLabel =
		currentHermesMeta?.model ?? activeProfile?.model ?? selectedModelLabel ?? '';
	const modelSource =
		currentHermesMeta?.model
			? 'session'
			: activeProfile?.model
				? 'profile'
				: selectedModelLabel
					? 'fallback'
					: 'unknown';

	return {
		workspaceLabel:
			activeWorkspaceItem?.name ??
			formatWorkspaceNameFromPath(
				workspaceStatus?.currentPath ??
					workspaces?.last_workspace ??
					workspaces?.items?.at(0)?.path ??
					''
			),
		workspacePath:
			workspaceStatus?.currentPath ?? activeWorkspaceItem?.path ?? workspaces?.last_workspace ?? '',
		workspaceSource: workspaceStatus?.source ?? (activeWorkspaceItem ? 'hermes' : 'stub'),
		profileLabel:
			currentHermesMeta?.profile ?? runtime?.active_profile ?? activeProfile?.name ?? '',
		sessionStateLabel: getHermesSessionStateLabelKey({
			temporaryChatEnabled,
			currentHermesSessionId: currentHermesMeta?.session_id,
			currentMessageId
		}),
		sessionId: currentHermesMeta?.session_id ?? null,
		targetId: currentHermesMeta?.target_id ?? runtime?.target_id ?? null,
		activeModelLabel,
		modelSource,
		browserFallbackModelLabel: selectedModelLabel || '',
		workspaceVisibleCount:
			typeof workspaceStatus?.visibleItemCount === 'number'
				? workspaceStatus.visibleItemCount
				: typeof workspaceStatus?.itemCount === 'number'
					? workspaceStatus.itemCount
					: null,
		linkedFileCount:
			typeof workspaceStatus?.linkedItemCount === 'number'
				? workspaceStatus.linkedItemCount
				: null,
		generatedFileCount,
		chatAttachedFileCount,
		taskCount,
		profileSkillCount:
			typeof activeProfile?.skill_count === 'number' ? activeProfile.skill_count : null,
		profileMemoryEnabled:
			typeof activeProfile?.memory_enabled === 'boolean'
				? activeProfile.memory_enabled
				: typeof activeProfile?.has_memory === 'boolean'
					? activeProfile.has_memory
					: null,
		userProfileEnabled:
			typeof activeProfile?.user_profile_enabled === 'boolean'
				? activeProfile.user_profile_enabled
				: typeof activeProfile?.has_user_profile === 'boolean'
					? activeProfile.has_user_profile
					: null
	};
};
