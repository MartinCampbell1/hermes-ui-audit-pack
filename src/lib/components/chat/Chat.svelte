<script lang="ts">
	import { v4 as uuidv4 } from 'uuid';
	import { toast } from 'svelte-sonner';
	import { PaneGroup, Pane, PaneResizer } from 'paneforge';

	import { getContext, onDestroy, onMount, tick } from 'svelte';
import { fade } from 'svelte/transition';
const i18n: Writable<i18nType> = getContext('i18n');
const HERMES_ONLY_CHAT = true;

	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { get, type Unsubscriber, type Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import {
		chatId,
		chats,
		config,
		type Model,
		models,
		tags as allTags,
		settings,
		showSidebar,
		WEBUI_NAME,
		banners,
		user,
		socket,
		audioQueue,
		showControls,
		showCallOverlay,
		currentChatPage,
		temporaryChatEnabled,
		mobile,
		chatTitle,
		showArtifacts,
		artifactContents,
		tools,
		toolServers,
		terminalServers,
		functions,
		selectedFolder,
		pinnedChats,
		showEmbeds,
		selectedTerminalId,
		showFileNavPath,
		showFileNavDir,
		chatRequestQueues,
		hermesContextLoaded,
		hermesRuntimeStore
	} from '$lib/stores';

	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import {
		convertMessagesToHistory,
		copyToClipboard,
		getMessageContentParts,
		createMessagesList,
		getPromptVariables,
		processDetails,
		removeAllDetails,
		getCodeBlockContents,
		isYoutubeUrl,
		displayFileHandler
	} from '$lib/utils';
	import { AudioQueue } from '$lib/utils/audio';

	import {
		archiveChatById,
		createNewChat,
		getAllTags,
		getChatById,
		getChatList,
		getPinnedChatList,
		getTagsById,
		updateChatById,
		updateChatFolderIdById
	} from '$lib/apis/chats';
	import {
		cancelHermesSessionMessageStream,
		getHermesSessionMessageStream,
		getHermesSessionMessageStreamStatus,
		respondHermesSessionApproval,
		startHermesSessionMessageStream
	} from '$lib/apis/hermes';
	import { generateOpenAIChatCompletion } from '$lib/apis/openai';
	import { processWeb, processWebSearch, processYoutubeVideo } from '$lib/apis/retrieval';
	import { getAndUpdateUserLocation, getUserSettings } from '$lib/apis/users';
	import {
		chatCompleted,
		generateQueries,
		chatAction,
		generateMoACompletion,
		stopTask,
		getTaskIdsByChatId
	} from '$lib/apis';
	import { getTools } from '$lib/apis/tools';
	import { uploadFile } from '$lib/apis/files';
	import { createOpenAITextStream } from '$lib/apis/streaming';
	import { getFunctions } from '$lib/apis/functions';
	import { updateFolderById } from '$lib/apis/folders';

	import Banner from '../common/Banner.svelte';
	import MessageInput from '$lib/components/chat/MessageInput.svelte';
	import Messages from '$lib/components/chat/Messages.svelte';
	import Navbar from '$lib/components/chat/Navbar.svelte';
	import ChatControls from './ChatControls.svelte';
	import EventConfirmDialog from '../common/ConfirmDialog.svelte';
	import Placeholder from './Placeholder.svelte';
	import FilesOverlay from './MessageInput/FilesOverlay.svelte';
	import NotificationToast from '../NotificationToast.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import HermesApprovalCard from '$lib/components/hermes/transcript/HermesApprovalCard.svelte';
	import HermesComposerActivityStrip from '$lib/components/hermes/transcript/HermesComposerActivityStrip.svelte';
	import Sidebar from '../icons/Sidebar.svelte';
	import Image from '../common/Image.svelte';
	import { getBanners } from '$lib/apis/configs';
	import {
		getHermesTargetId,
		refreshHermesSessionStores,
		getResolvedHermesSessionContext,
		HERMES_DEFAULT_TARGET_ID
	} from '$lib/utils/hermesSessions';
	import {
		getCurrentBranchLatestAssistantMessageId,
		getHermesComposerActivityMessageId,
		normalizeHermesStreamEventName,
		upsertHermesToolExecution
	} from '$lib/utils/hermesTranscript';
	import { ensureHermesContextBundle } from '$lib/utils/hermesContext';

	export let chatIdProp = '';

	let loading = true;

	const eventTarget = new EventTarget();
	let controlPane: Pane | undefined;
	let controlPaneComponent: ChatControls | undefined;

	let messageInput: MessageInput | undefined;

	let autoScroll = true;
	let processing = '';
	let messagesContainerElement: HTMLDivElement;

	let navbarElement;

	let showEventConfirmation = false;
	let eventConfirmationTitle = '';
	let eventConfirmationMessage = '';
	let eventConfirmationInput = false;
	let eventConfirmationInputPlaceholder = '';
	let eventConfirmationInputValue = '';
	let eventConfirmationInputType = '';
	let eventCallback = null;

	type HermesApprovalResolution = 'once' | 'session' | 'always' | 'deny';
	type HermesApprovalCallback = (resolution: HermesApprovalResolution) => void | Promise<void>;
	type HermesPersistedActiveStream = {
		clientRequestId: string;
		responseMessageId: string;
		streamId?: string | null;
		sessionId?: string | null;
		targetId?: string | null;
		pendingApproval?: {
			title?: string;
			description?: string;
			riskLevel?: 'low' | 'medium' | 'high';
		} | null;
		updatedAt: number;
	};

	const approvalCallbacks = new Map<string, HermesApprovalCallback>();
	const HERMES_ACTIVE_STREAM_STORAGE_PREFIX = 'hermes-active-stream';

	const attachInlineApproval = (
		messageId: string,
		data: {
			title?: string;
			message?: string;
			description?: string;
			riskLevel?: 'low' | 'medium' | 'high';
		},
		callback: HermesApprovalCallback | null = null
	) => {
		const message = history.messages[messageId];

		if (!message || message.role !== 'assistant') {
			return false;
		}

		if (callback) {
			approvalCallbacks.set(messageId, callback);
		}

		message.hermesApproval = {
			title: data?.title ?? $i18n.t('Approval required'),
			description: data?.description ?? data?.message ?? '',
			riskLevel: data?.riskLevel,
			state: 'pending',
			interactive: !!callback
		};

		history.messages[messageId] = message;
		return true;
	};

	const respondToApproval = async (messageId: string, resolution: HermesApprovalResolution) => {
		const messages = history.messages as Record<string, any>;
		const message = messages[messageId];

		if (!message?.hermesApproval) {
			return;
		}

		const callback = approvalCallbacks.get(messageId);

		if (callback) {
			try {
				await callback(resolution);
			} catch (error) {
				console.error('Error responding to approval:', error);
				toast.error(
					typeof error === 'string'
						? error
						: (error?.message ?? $i18n.t('Failed to resolve Hermes approval.'))
				);
				return;
			}

			approvalCallbacks.delete(messageId);
		}

		message.hermesApproval = {
			...message.hermesApproval,
			state: 'resolved',
			resolution,
			interactive: false
		};

		messages[messageId] = message;
	};

	const upsertHermesSessionStatus = (
		message,
		{
			description,
			done = false
		}: {
			description: string;
			done?: boolean;
		}
	) => {
		const statusEntries = [...(message?.statusHistory ?? [])];
		const statusIndex = statusEntries.findIndex((entry) => entry?.action === 'hermes_session');
		const nextStatus = {
			action: 'hermes_session',
			description,
			done,
			hidden: false,
			query: ''
		};

		if (statusIndex === -1) {
			statusEntries.push(nextStatus);
		} else {
			statusEntries[statusIndex] = {
				...statusEntries[statusIndex],
				...nextStatus
			};
		}

		message.statusHistory = statusEntries;
		return message;
	};

	const appendHermesToolStatus = (message, toolEvent) => {
		const toolName = toolEvent?.name ? `${toolEvent.name}` : $i18n.t('Tool activity');
		const preview =
			(toolEvent?.preview ?? toolEvent?.message ?? toolEvent?.command ?? '')
				? `${toolEvent?.preview ?? toolEvent?.message ?? toolEvent?.command}`.trim()
				: '';
		const toolState =
			toolEvent?.event === 'tool.error' || toolEvent?.error
				? 'failed'
				: toolEvent?.event === 'tool.finished' ||
					  toolEvent?.event === 'tool.completed' ||
					  toolEvent?.done === true ||
					  toolEvent?.result
					? 'done'
					: 'running';
		const description = preview ? `${toolName}: ${preview}` : toolName;

		message.statusHistory = [
			...(message?.statusHistory ?? []),
			{
				action: 'hermes_tool',
				description,
				done: toolState !== 'running',
				hidden: false,
				query: ''
			}
		];

		return message;
	};

	let selectedModels = [''];
	let atSelectedModel: Model | undefined;
	let selectedModelIds = [];
	$: if (atSelectedModel !== undefined) {
		selectedModelIds = [atSelectedModel.id];
	} else {
		selectedModelIds = selectedModels;
	}

	let selectedToolIds = [];
	let selectedFilterIds = [];
	let pendingOAuthTools = [];

	let imageGenerationEnabled = false;
	let webSearchEnabled = false;
	let codeInterpreterEnabled = false;

	let showCommands = false;

	let generating = false;
	let dragged = false;
	let generationController = null;
	let hermesActiveStreamId: string | null = null;
	let hasPersistedHermesActiveStream = false;

	let chat = null;
	let tags = [];

	let history = {
		messages: {},
		currentId: null
	};

	const loadHermesRuntimeContext = async (force = false) => {
		if (typeof localStorage === 'undefined') {
			return $hermesRuntimeStore;
		}

		await ensureHermesContextBundle(localStorage.token, { force, includeProfiles: false });
		return $hermesRuntimeStore;
	};

	const withHermesRuntimeContext = async (chatPayload: Record<string, any>) => {
		const persistedContext = getResolvedHermesSessionContext({
			session:
				chatPayload?.hermesSession && typeof chatPayload.hermesSession === 'object'
					? chatPayload.hermesSession
					: chat?.chat?.hermesSession ?? null,
			meta: chat?.meta ?? null
		});
		if (persistedContext) {
			return {
				...chatPayload,
				hermesSession: persistedContext
			};
		}

		const runtime = await loadHermesRuntimeContext();
		const hermesSession = getResolvedHermesSessionContext({ runtime });

		return hermesSession
			? {
					...chatPayload,
					hermesSession
				}
			: chatPayload;
	};

	$: currentHermesSessionContext = getResolvedHermesSessionContext({
		session: chat?.chat?.hermesSession ?? null,
		meta: chat?.meta ?? null,
		runtime: $hermesRuntimeStore
	});

	const getCurrentHermesSessionContext = () => currentHermesSessionContext;

	const getCurrentHermesTargetId = (
		hermesSessionContext: Record<string, any> | null = getCurrentHermesSessionContext()
	) => getHermesTargetId(hermesSessionContext ?? $hermesRuntimeStore ?? HERMES_DEFAULT_TARGET_ID);

	const canStartNewHermesSessionFromSurface = (
		hermesSessionContext: Record<string, any> | null,
		messageHistory: { messages?: Record<string, any> } | null = history
	) => {
		if (hermesSessionContext?.session_id) {
			return false;
		}

		const messages = Object.values(messageHistory?.messages ?? {}) as Record<string, any>[];
		const hasConversationHistory =
			messages.length > 0 &&
			!messages.every((message) => {
				if (message?.role === 'user') {
					return !message?.parentId;
				}

				if (message?.role === 'assistant') {
					return (
						typeof message?.parentId === 'string' &&
						(message?.content ?? '') === '' &&
						message?.done === false
					);
				}

				return false;
			});

		return (
			!hasConversationHistory &&
			(!!hermesSessionContext?.active_home || !!hermesSessionContext?.profile)
		);
	};

	const refreshHermesSessionSurfacing = async () => {
		if (typeof localStorage === 'undefined' || !localStorage.token) {
			return;
		}

		const sessions = await refreshHermesSessionStores(localStorage.token).catch((error) => {
			console.debug('Failed to refresh Hermes sessions after chat update:', error);
			return null;
		});

		if (!sessions) {
			return;
		}
	};

	const getHermesActiveStreamStorageKey = (
		targetChatId: string | null | undefined,
		targetId: string | null | undefined = null
	) => {
		if (!targetChatId || targetChatId.startsWith('local:')) {
			return null;
		}

		return `${HERMES_ACTIVE_STREAM_STORAGE_PREFIX}:${getHermesTargetId(targetId)}:${targetChatId}`;
	};

	const getLegacyHermesActiveStreamStorageKey = (targetChatId: string | null | undefined) => {
		if (!targetChatId || targetChatId.startsWith('local:')) {
			return null;
		}

		return `${HERMES_ACTIVE_STREAM_STORAGE_PREFIX}:${targetChatId}`;
	};

	const readPersistedHermesActiveStream = (
		targetChatId: string | null | undefined,
		targetId: string | null | undefined = null
	): HermesPersistedActiveStream | null => {
		if (typeof sessionStorage === 'undefined') {
			return null;
		}

		const storageKey = getHermesActiveStreamStorageKey(targetChatId, targetId);
		const legacyStorageKey = getLegacyHermesActiveStreamStorageKey(targetChatId);
		if (!storageKey && !legacyStorageKey) {
			return null;
		}

		const raw = (storageKey ? sessionStorage.getItem(storageKey) : null) ??
			(legacyStorageKey ? sessionStorage.getItem(legacyStorageKey) : null);
		if (!raw) {
			return null;
		}

		try {
			const parsed = JSON.parse(raw);
			if (
				typeof parsed?.clientRequestId === 'string' &&
				typeof parsed?.responseMessageId === 'string' &&
				(parsed?.streamId == null || typeof parsed?.streamId === 'string') &&
				typeof parsed?.updatedAt === 'number'
			) {
				const normalizedTargetId = getHermesTargetId(parsed?.targetId ?? targetId);
				const normalizedPayload = {
					...parsed,
					targetId: normalizedTargetId
				} as HermesPersistedActiveStream;

				if (legacyStorageKey && storageKey && legacyStorageKey !== storageKey) {
					sessionStorage.removeItem(legacyStorageKey);
					sessionStorage.setItem(
						storageKey,
						JSON.stringify({
							...normalizedPayload,
							updatedAt: Date.now()
						})
					);
				}

				return normalizedPayload;
			}
		} catch (error) {
			console.warn('Failed to parse persisted Hermes active stream state:', error);
		}

		if (storageKey) {
			sessionStorage.removeItem(storageKey);
		}
		if (legacyStorageKey && legacyStorageKey !== storageKey) {
			sessionStorage.removeItem(legacyStorageKey);
		}
		return null;
	};

	const persistHermesActiveStream = (
		targetChatId: string | null | undefined,
		targetId: string | null | undefined,
		payload: HermesPersistedActiveStream | null
	) => {
		if (typeof sessionStorage === 'undefined') {
			return;
		}

		const storageKey = getHermesActiveStreamStorageKey(targetChatId, targetId);
		const legacyStorageKey = getLegacyHermesActiveStreamStorageKey(targetChatId);
		if (!storageKey && !legacyStorageKey) {
			return;
		}

		if (!payload) {
			if (storageKey) {
				sessionStorage.removeItem(storageKey);
			}
			if (legacyStorageKey && legacyStorageKey !== storageKey) {
				sessionStorage.removeItem(legacyStorageKey);
			}
			if (targetChatId === chatIdProp) {
				hasPersistedHermesActiveStream = false;
			}
			return;
		}

		if (legacyStorageKey && legacyStorageKey !== storageKey) {
			sessionStorage.removeItem(legacyStorageKey);
		}

		if (storageKey) {
			sessionStorage.setItem(
				storageKey,
				JSON.stringify({
					...payload,
					targetId: getHermesTargetId(payload?.targetId ?? targetId),
					updatedAt: Date.now()
				})
			);
		}

		if (targetChatId === chatIdProp) {
			hasPersistedHermesActiveStream = true;
		}
	};

	const updatePersistedHermesActiveStream = (
		targetChatId: string | null | undefined,
		targetId: string | null | undefined,
		update: Partial<HermesPersistedActiveStream>
	) => {
		const existing = readPersistedHermesActiveStream(targetChatId, targetId);
		if (!existing) {
			return;
		}

		persistHermesActiveStream(targetChatId, targetId, {
			...existing,
			...update,
			updatedAt: Date.now()
		});
	};

	const buildHermesApprovalPayload = (data: Record<string, any> = {}) => ({
		title: data?.title ?? $i18n.t('Approval required'),
		description:
			data?.description ?? data?.message ?? data?.preview ?? data?.command ?? data?.tool_name ?? '',
		riskLevel: data?.riskLevel ?? data?.risk_level ?? 'medium'
	});

	const handleHermesProfileSwitched = async () => {
		await loadHermesRuntimeContext(true);
		await refreshHermesSessionSurfacing();
	};

	$: hasPersistedHermesActiveStream =
		typeof sessionStorage !== 'undefined'
			? !!readPersistedHermesActiveStream(chatIdProp, getCurrentHermesTargetId())
			: false;

	const finalizeHermesCompletedStream = async ({
		responseMessageId,
		targetChatId,
		hermesSessionContext,
		payload
	}: {
		responseMessageId: string;
		targetChatId: string;
		hermesSessionContext: Record<string, any> | null;
		payload: Record<string, any>;
	}) => {
		const activeTargetId = getHermesTargetId(
			payload?.chat?.hermesSession ?? hermesSessionContext ?? payload?.meta?.hermes ?? null
		);
		const responseMessage = history.messages[responseMessageId];
		if (!responseMessage) {
			persistHermesActiveStream(targetChatId, activeTargetId, null);
			return;
		}

		persistHermesActiveStream(targetChatId, activeTargetId, null);
		upsertHermesSessionStatus(responseMessage, {
			description: $i18n.t('Hermes session response received'),
			done: true
		});
		responseMessage.done = true;
		if (payload?.result?.usage) {
			responseMessage.usage = payload.result.usage;
		}
		history.messages[responseMessageId] = responseMessage;

		if (!payload?.chat?.history) {
			throw new Error('Hermes response did not include chat history.');
		}

		const hermesChatPayload = await withHermesRuntimeContext({
			...payload.chat,
			hermesSession: {
				...hermesSessionContext,
				...(payload.chat?.hermesSession ?? {}),
				session_id: payload.session_id ?? hermesSessionContext?.session_id ?? null,
				target_id:
					payload.chat?.hermesSession?.target_id ??
					payload.chat?.hermesSession?.runtime_target_id ??
					hermesSessionContext?.target_id ??
					hermesSessionContext?.runtime_target_id ??
					activeTargetId,
				runtime_target_id:
					payload.chat?.hermesSession?.runtime_target_id ??
					payload.chat?.hermesSession?.target_id ??
					hermesSessionContext?.runtime_target_id ??
					hermesSessionContext?.target_id ??
					activeTargetId
			}
		});

		history = hermesChatPayload.history ?? history;
		params = hermesChatPayload.params ?? {};
		chatFiles = hermesChatPayload.files ?? [];
		selectedModels = normalizeSelectedModels(hermesChatPayload.models ?? selectedModels);
		chatTitle.set(hermesChatPayload.title ?? $chatTitle);

		if ($chatId == targetChatId && !$temporaryChatEnabled) {
			chat = await updateChatById(localStorage.token, targetChatId, hermesChatPayload);
			currentChatPage.set(1);
			await chats.set(await getChatList(localStorage.token, $currentChatPage));
		}

		await refreshHermesSessionSurfacing();
		await processNextInQueue(targetChatId);
	};

	const finalizeHermesInterruptedStream = async ({
		responseMessageId,
		targetChatId,
		description,
		errorMessage = null
	}: {
		responseMessageId: string;
		targetChatId: string;
		description: string;
		errorMessage?: string | null;
	}) => {
		const activeTargetId = getCurrentHermesTargetId();
		const responseMessage = history.messages[responseMessageId];
		if (!responseMessage) {
			persistHermesActiveStream(targetChatId, activeTargetId, null);
			return;
		}

		persistHermesActiveStream(targetChatId, activeTargetId, null);
		upsertHermesSessionStatus(responseMessage, {
			description,
			done: true
		});
		responseMessage.done = true;

		if (errorMessage) {
			responseMessage.error = {
				content: errorMessage
			};
		}

		if (responseMessage.hermesApproval) {
			responseMessage.hermesApproval = {
				...responseMessage.hermesApproval,
				interactive: false
			};
		}

		history.messages[responseMessageId] = responseMessage;
		history.currentId = responseMessageId;
		history = history;
	};

	const attachHermesStreamApproval = (
		responseMessageId: string,
		streamId: string,
		targetChatId: string,
		data: Record<string, any> = {}
	) => {
		const activeTargetId = getCurrentHermesTargetId();
		const approval = buildHermesApprovalPayload(data);
		const attached = attachInlineApproval(responseMessageId, approval, async (resolution) => {
			await respondHermesSessionApproval(localStorage.token, {
				stream_id: streamId,
				choice: resolution,
				target_id: activeTargetId
			});
		});

		if (attached) {
			updatePersistedHermesActiveStream(targetChatId, activeTargetId, {
				pendingApproval: approval
			});
		}

		return attached;
	};

	const getPendingComposerApprovalMessageId = (messageHistory: {
		currentId?: string | null;
		messages?: Record<string, any>;
	}) => {
		const messages = messageHistory?.messages ?? {};
		const seen = new Set<string>();
		let messageId = messageHistory?.currentId ?? null;

		while (messageId && !seen.has(messageId)) {
			const message = messages[messageId];
			if (!message) {
				break;
			}

			if (message.role === 'assistant' && message?.hermesApproval?.state === 'pending') {
				return messageId;
			}

			seen.add(messageId);
			messageId = message.parentId ?? null;
		}

		return null;
	};

	const getRecoverableHermesPendingStream = () => {
		const responseMessageId = getCurrentBranchLatestAssistantMessageId(history);
		if (!responseMessageId) {
			return null;
		}

		const responseMessage = history.messages?.[responseMessageId];
		if (
			!responseMessage ||
			responseMessage.role !== 'assistant' ||
			responseMessage.done !== false ||
			(!responseMessage.hermesStartIntent && !responseMessage.hermesClientRequestId)
		) {
			return null;
		}

		return {
			clientRequestId: responseMessage.hermesClientRequestId ?? responseMessageId,
			responseMessageId,
			streamId: null,
			sessionId: getCurrentHermesSessionContext()?.session_id ?? null,
			targetId: getCurrentHermesTargetId(),
			pendingApproval: null,
			updatedAt: Date.now()
		} satisfies HermesPersistedActiveStream;
	};

	const getMessageStatusUpdatesEnabled = (message: any) => {
		const model = $models.find((item) => item.id === message?.model);
		return model?.info?.meta?.capabilities?.status_updates ?? true;
	};

	const getAvailableModelIds = () =>
		$models.filter((model) => !(model?.info?.meta?.hidden ?? false)).map((model) => model.id);

	const normalizeSelectedModels = (candidateModels: unknown) => {
		const availableModelIds = getAvailableModelIds();
		const candidateList = Array.isArray(candidateModels)
			? candidateModels
			: typeof candidateModels === 'string' && candidateModels.length > 0
				? candidateModels.split(',')
				: [];

		const normalized: string[] = [];

		for (const candidateModelId of candidateList) {
			if (typeof candidateModelId !== 'string') {
				continue;
			}

			const modelId = candidateModelId.trim();
			if (!modelId || !availableModelIds.includes(modelId) || normalized.includes(modelId)) {
				continue;
			}

			normalized.push(modelId);
		}

		if (normalized.length > 0) {
			return normalized;
		}

		return availableModelIds.length > 0 ? [availableModelIds[0]] : [];
	};

	$: composerPendingApprovalMessageId = getPendingComposerApprovalMessageId(history);
	$: composerPendingApproval = composerPendingApprovalMessageId
		? (history.messages?.[composerPendingApprovalMessageId]?.hermesApproval ?? null)
		: null;
	$: composerActivityCandidateMessageId = getCurrentBranchLatestAssistantMessageId(history);
	$: composerActivityCandidateMessage = composerActivityCandidateMessageId
		? (history.messages?.[composerActivityCandidateMessageId] ?? null)
		: null;
	$: composerActivityMessageId = getHermesComposerActivityMessageId(history, {
		statusUpdatesEnabled: getMessageStatusUpdatesEnabled(composerActivityCandidateMessage)
	});
	$: composerActivityMessage = composerActivityMessageId
		? (history.messages?.[composerActivityMessageId] ?? null)
		: null;

	let taskIds = null;

	// Chat Input
	let prompt = '';
	let chatFiles = [];
	let files = [];
	let params = {};

	$: if (chatIdProp) {
		navigateHandler();
	}

	const navigateHandler = async () => {
		loading = true;
		approvalCallbacks.clear();

		prompt = '';
		messageInput?.setText('');

		files = [];
		selectedToolIds = [];
		selectedFilterIds = [];
		webSearchEnabled = false;
		imageGenerationEnabled = false;

		const storageChatInput = sessionStorage.getItem(
			`chat-input${chatIdProp ? `-${chatIdProp}` : ''}`
		);

		if (chatIdProp && (await loadChat())) {
			await tick();
			loading = false;
			window.setTimeout(() => scrollToBottom(), 0);

			await tick();

			// Process any queued requests if the chat is idle
			const lastMessage = history.currentId ? history.messages[history.currentId] : null;
			const isIdle = !lastMessage || lastMessage.role !== 'assistant' || lastMessage.done;
			if (isIdle) {
				await processNextInQueue(chatIdProp);
			}

			if (storageChatInput) {
				try {
					const input = JSON.parse(storageChatInput);

					if (!$temporaryChatEnabled) {
						messageInput?.setText(input.prompt);
						files = input.files;
						selectedToolIds = input.selectedToolIds;
						selectedFilterIds = input.selectedFilterIds;
						webSearchEnabled = input.webSearchEnabled;
						imageGenerationEnabled = input.imageGenerationEnabled;
						codeInterpreterEnabled = input.codeInterpreterEnabled;
					}
				} catch (e) {}
			} else {
				await setDefaults();
			}

			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		} else {
			await goto('/');
		}
	};

	const onSelect = async (e) => {
		const { type, data } = e;

		if (type === 'prompt') {
			// Handle prompt selection
			messageInput?.setText(data, async () => {
				if (!($settings?.insertSuggestionPrompt ?? false)) {
					await tick();
					submitPrompt(prompt);
				}
			});
		}
	};

	$: if (selectedModels && chatIdProp !== '') {
		saveSessionSelectedModels();
	}

	const saveSessionSelectedModels = () => {
		const selectedModelsString = JSON.stringify(selectedModels);
		if (
			selectedModels.length === 0 ||
			(selectedModels.length === 1 && selectedModels[0] === '') ||
			sessionStorage.selectedModels === selectedModelsString
		) {
			return;
		}
		sessionStorage.selectedModels = selectedModelsString;
		console.log('saveSessionSelectedModels', selectedModels, sessionStorage.selectedModels);
	};

	let oldSelectedModelIds = [''];
	$: if (JSON.stringify(selectedModelIds) !== JSON.stringify(oldSelectedModelIds)) {
		onSelectedModelIdsChange();
	}

	const onSelectedModelIdsChange = () => {
		resetInput();
		oldSelectedModelIds = structuredClone(selectedModelIds);
	};

	const resetInput = () => {
		selectedToolIds = [];
		selectedFilterIds = [];
		pendingOAuthTools = [];
		webSearchEnabled = false;
		imageGenerationEnabled = false;
		codeInterpreterEnabled = false;

		if (selectedModelIds.filter((id) => id).length > 0) {
			setDefaults();
		}
	};

	const setDefaults = async () => {
		if (!$tools) {
			tools.set(await getTools(localStorage.token));
		}
		if (!$functions) {
			functions.set(await getFunctions(localStorage.token));
		}
		if (selectedModels.length !== 1 && !atSelectedModel) {
			return;
		}

		const model = atSelectedModel ?? $models.find((m) => m.id === selectedModels[0]);
		if (model) {
			// Set Default Tools
			if (model?.info?.meta?.toolIds) {
				const defaultIds = [
					...new Set(
						[...(model?.info?.meta?.toolIds ?? [])].filter((id) => $tools.find((t) => t.id === id))
					)
				];

				// Separate unauthenticated OAuth tools
				const unauthed = [];
				const authed = [];
				for (const id of defaultIds) {
					const tool = $tools.find((t) => t.id === id);
					if (tool && tool.authenticated === false) {
						const parts = id.split(':');
						const serverId = parts.at(-1) ?? id;
						const authType =
							parts.length > 1 ? (parts[0] === 'server' ? parts[1] : parts[0]) : null;
						unauthed.push({ id, name: tool.name ?? id, serverId, authType });
					} else {
						authed.push(id);
					}
				}
				selectedToolIds = authed;
				pendingOAuthTools = unauthed;
			} else if ($settings?.tools) {
				selectedToolIds = $settings.tools;
			} else {
				selectedToolIds = selectedToolIds.filter((id) => !id.startsWith('direct_server:'));
			}

			// Set Default Filters (Toggleable only)
			if (model?.info?.meta?.defaultFilterIds) {
				selectedFilterIds = model.info.meta.defaultFilterIds.filter((id) =>
					model?.filters?.find((f) => f.id === id)
				);
			}

			// Set Default Features
			if (model?.info?.meta?.defaultFeatureIds) {
				if (
					model.info?.meta?.capabilities?.['image_generation'] &&
					$config?.features?.enable_image_generation &&
					($user?.role === 'admin' || $user?.permissions?.features?.image_generation)
				) {
					imageGenerationEnabled = model.info.meta.defaultFeatureIds.includes('image_generation');
				}

				if (
					model.info?.meta?.capabilities?.['web_search'] &&
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
				) {
					webSearchEnabled = model.info.meta.defaultFeatureIds.includes('web_search');
				}

				if (
					model.info?.meta?.capabilities?.['code_interpreter'] &&
					$config?.features?.enable_code_interpreter &&
					($user?.role === 'admin' || $user?.permissions?.features?.code_interpreter)
				) {
					codeInterpreterEnabled = model.info.meta.defaultFeatureIds.includes('code_interpreter');
				}
			}
		}
	};

	const showMessage = async (message, scroll = true) => {
		const _chatId = JSON.parse(JSON.stringify($chatId));
		let _messageId = JSON.parse(JSON.stringify(message.id));

		let messageChildrenIds = [];
		if (_messageId === null) {
			messageChildrenIds = Object.keys(history.messages).filter(
				(id) => history.messages[id].parentId === null
			);
		} else {
			messageChildrenIds = history.messages[_messageId].childrenIds;
		}

		while (messageChildrenIds.length !== 0) {
			_messageId = messageChildrenIds.at(-1);
			messageChildrenIds = history.messages[_messageId].childrenIds;
		}

		history.currentId = _messageId;

		await tick();

		if (($settings?.scrollOnBranchChange ?? true) && scroll) {
			const messageElement = document.getElementById(`message-${message.id}`);
			if (messageElement) {
				messageElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
			}
		}

		await tick();
		await tick();
		await tick();

		saveChatHandler(_chatId, history);
	};

	const terminalEventHandler = (type: string, data: any) => {
		if (type === 'terminal:display_file') {
			if (!data?.path) return;
			displayFileHandler(data.path, { showControls, showFileNavPath });
		} else if (type === 'terminal:write_file' || type === 'terminal:replace_file_content') {
			if (!data?.path) return;
			showFileNavDir.set(data.path);
		} else if (type === 'terminal:run_command') {
			showFileNavDir.set('/');
		}
	};

	const chatEventHandler = async (event, cb) => {
		console.log(event);

		if (event.chat_id === $chatId) {
			await tick();
			let message = history.messages[event.message_id];

			if (message) {
				const type = event?.data?.type ?? null;
				const data = event?.data?.data ?? null;

				if (type === 'status') {
					if (message?.statusHistory) {
						message.statusHistory.push(data);
					} else {
						message.statusHistory = [data];
					}
				} else if (type === 'chat:completion') {
					chatCompletionEventHandler(data, message, event.chat_id);
				} else if (type === 'chat:tasks:cancel') {
					if (event.message_id === history.currentId) {
						taskIds = null;
						// Set all response messages to done
						for (const messageId of history.messages[message.parentId].childrenIds) {
							history.messages[messageId].done = true;
						}
						await processNextInQueue($chatId);
					} else {
						message.done = true;
					}
				} else if (type === 'chat:message:delta' || type === 'message') {
					message.content += data.content;
				} else if (type === 'chat:message' || type === 'replace') {
					message.content = data.content;
				} else if (type === 'chat:message:files' || type === 'files') {
					message.files = data.files;
				} else if (type === 'chat:message:embeds' || type === 'embeds') {
					message.embeds = data.embeds;

					// Auto-scroll to the embed once it's rendered in the DOM
					await tick();
					setTimeout(() => {
						const embedEl = document.getElementById(`${event.message_id}-embeds-container`);
						if (embedEl) {
							embedEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
						}
					}, 100);
				} else if (type === 'chat:message:error') {
					message.error = data.error;
				} else if (type === 'chat:message:follow_ups') {
					message.followUps = data.follow_ups;

					if (autoScroll) {
						scrollToBottom('smooth');
					}
				} else if (type === 'chat:message:favorite') {
					// Update message favorite status
					message.favorite = data.favorite;
				} else if (type === 'chat:title') {
					chatTitle.set(data);
					currentChatPage.set(1);
					await chats.set(await getChatList(localStorage.token, $currentChatPage));
				} else if (type === 'chat:tags') {
					chat = await getChatById(localStorage.token, $chatId);
					allTags.set(await getAllTags(localStorage.token));
				} else if (type === 'source' || type === 'citation') {
					if (data?.type === 'code_execution') {
						// Code execution; update existing code execution by ID, or add new one.
						if (!message?.code_executions) {
							message.code_executions = [];
						}

						const existingCodeExecutionIndex = message.code_executions.findIndex(
							(execution) => execution.id === data.id
						);

						if (existingCodeExecutionIndex !== -1) {
							message.code_executions[existingCodeExecutionIndex] = data;
						} else {
							message.code_executions.push(data);
						}

						message.code_executions = message.code_executions;
					} else {
						// Regular source.
						if (message?.sources) {
							message.sources.push(data);
						} else {
							message.sources = [data];
						}
					}
				} else if (type === 'notification') {
					const toastType = data?.type ?? 'info';
					const toastContent = data?.content ?? '';

					if (toastType === 'success') {
						toast.success(toastContent);
					} else if (toastType === 'error') {
						toast.error(toastContent);
					} else if (toastType === 'warning') {
						toast.warning(toastContent);
					} else {
						toast.info(toastContent);
					}
				} else if (type === 'confirmation') {
					if (
						event.message_id &&
						attachInlineApproval(
							event.message_id,
							data,
							cb ? async (resolution) => await cb(resolution !== 'deny') : null
						)
					) {
						await tick();
						if (autoScroll) {
							scrollToBottom('smooth');
						}
					} else {
						eventCallback = cb;

						eventConfirmationInput = false;
						showEventConfirmation = true;

						eventConfirmationTitle = data.title;
						eventConfirmationMessage = data.message;
					}
				} else if (type === 'execute') {
					eventCallback = cb;

					try {
						// Use Function constructor to evaluate code in a safer way
						const asyncFunction = new Function(`return (async () => { ${data.code} })()`);
						const result = await asyncFunction(); // Await the result of the async function

						if (cb) {
							cb(result);
						}
					} catch (error) {
						console.error('Error executing code:', error);
					}
				} else if (type === 'input') {
					eventCallback = cb;

					eventConfirmationInput = true;
					showEventConfirmation = true;

					eventConfirmationTitle = data.title;
					eventConfirmationMessage = data.message;
					eventConfirmationInputPlaceholder = data.placeholder;
					eventConfirmationInputValue = data?.value ?? '';
					eventConfirmationInputType = data?.type ?? '';
				} else if (type.startsWith('terminal:')) {
					terminalEventHandler(type, data);
				} else {
					console.log('Unknown message type', data);
				}

				history.messages[event.message_id] = message;
			}
		} else {
			// Non-active chat completion: queue stays in the global store.
			// navigateHandler will process it when the user returns to that chat.
		}
	};

	const onMessageHandler = async (event: {
		origin: string;
		data: { type: string; text: string };
	}) => {
		const isSameOrigin = event.origin === window.origin;
		const type = event.data?.type;

		// Prompt-related message types only submit text to the chat input —
		// functionally equivalent to the user typing.  When same-origin is
		// enabled they go through immediately.  When it is disabled (opaque
		// origin) we show a confirmation dialog so the user stays in control.
		const iframePromptTypes = ['input:prompt', 'input:prompt:submit', 'action:submit'];

		if (!isSameOrigin && !iframePromptTypes.includes(type)) {
			return;
		}

		if (type === 'action:submit') {
			console.debug(event.data.text);

			if (prompt !== '') {
				await tick();
				submitPrompt(prompt);
			}
		}

		if (type === 'input:prompt') {
			console.debug(event.data.text);

			const inputElement = document.getElementById('chat-input');

			if (inputElement) {
				messageInput?.setText(event.data.text);
				inputElement.focus();
			}
		}

		if (type === 'input:prompt:submit') {
			console.debug(event.data.text);

			if (event.data.text !== '') {
				if (isSameOrigin) {
					await tick();
					submitPrompt(event.data.text);
				} else {
					// Cross-origin: ask user to confirm before submitting
					eventConfirmationInput = false;
					eventConfirmationTitle = $i18n.t('Confirm Prompt from Embed');
					eventConfirmationMessage = event.data.text;
					eventCallback = async (confirmed: boolean) => {
						if (confirmed) {
							await tick();
							submitPrompt(event.data.text);
						}
					};
					showEventConfirmation = true;
				}
			}
		}
	};

	const savedModelIds = async () => {
		if (
			$selectedFolder &&
			selectedModels.filter((modelId) => modelId !== '').length > 0 &&
			JSON.stringify($selectedFolder?.data?.model_ids) !== JSON.stringify(selectedModels)
		) {
			const res = await updateFolderById(localStorage.token, $selectedFolder.id, {
				data: {
					model_ids: selectedModels
				}
			});
		}
	};

	$: if (selectedModels !== null) {
		savedModelIds();
	}

	const stopAudio = () => {
		try {
			speechSynthesis.cancel();
			$audioQueue?.stop();
		} catch {}
	};

	onMount(() => {
		console.log('mounted');
		window.addEventListener('message', onMessageHandler);
		$socket?.on('events', chatEventHandler);

		$audioQueue?.destroy();

		const audioQueueInstance = new AudioQueue(document.getElementById('audioElement'));
		audioQueue.set(audioQueueInstance);

		// Restore direct terminal enabled states based on persisted selectedTerminalId
		if ($settings?.terminalServers?.length) {
			settings.set({
				...$settings,
				terminalServers: ($settings.terminalServers ?? []).map((s) => ({
					...s,
					enabled: $selectedTerminalId !== null && s.url === $selectedTerminalId
				}))
			});
		}

		const pageSubscribe = page.subscribe(async (p) => {
			if (p.url.pathname === '/') {
				await tick();
				initNewChat();

				// Re-fetch banners on navigation to homepage so newly configured banners appear
				try {
					banners.set(await getBanners(localStorage.token).catch(() => []));
				} catch (e) {
					console.error('Failed to refresh banners:', e);
				}
			}

			stopAudio();
		});

		const showControlsSubscribe = showControls.subscribe(async (value) => {
			await tick();
			if (controlPane && !$mobile) {
				try {
					if (value) {
						controlPaneComponent?.openPane();
					} else {
						controlPane.collapse();
					}
				} catch (e) {
					// ignore
				}
			}

			if (!value) {
				showCallOverlay.set(false);
				showArtifacts.set(false);
				showEmbeds.set(false);
			}
		});

		const selectedFolderSubscribe = selectedFolder.subscribe(async (folder) => {
			await tick();
			if (
				folder?.data?.model_ids &&
				JSON.stringify(selectedModels) !== JSON.stringify(folder.data.model_ids)
			) {
				selectedModels = folder.data.model_ids;

				console.log('Set selectedModels from folder data:', selectedModels);
			}
		});

		const storageChatInput = sessionStorage.getItem(
			`chat-input${chatIdProp ? `-${chatIdProp}` : ''}`
		);

		const init = async () => {
			if (!chatIdProp) {
				loading = false;
				await tick();
			}

			if (storageChatInput) {
				prompt = '';
				messageInput?.setText('');

				files = [];
				selectedToolIds = [];
				selectedFilterIds = [];
				webSearchEnabled = false;
				imageGenerationEnabled = false;
				codeInterpreterEnabled = false;

				try {
					const input = JSON.parse(storageChatInput);

					if (!$temporaryChatEnabled) {
						messageInput?.setText(input.prompt);
						files = input.files;
						selectedToolIds = input.selectedToolIds;
						selectedFilterIds = input.selectedFilterIds;
						webSearchEnabled = input.webSearchEnabled;
						imageGenerationEnabled = input.imageGenerationEnabled;
						codeInterpreterEnabled = input.codeInterpreterEnabled;
					}
				} catch (e) {}
			}

			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		};
		init();

		return () => {
			try {
				approvalCallbacks.clear();
				pageSubscribe();
				showControlsSubscribe();
				selectedFolderSubscribe();
				window.removeEventListener('message', onMessageHandler);
				$socket?.off('events', chatEventHandler);
				audioQueueInstance?.destroy();
				audioQueue.set(null);
			} catch (e) {
				console.error(e);
			}
		};
	});

	// File upload functions

	const uploadGoogleDriveFile = async (fileData) => {
		console.log('Starting uploadGoogleDriveFile with:', {
			id: fileData.id,
			name: fileData.name,
			url: fileData.url,
			headers: {
				Authorization: `Bearer ${token}`
			}
		});

		// Validate input
		if (!fileData?.id || !fileData?.name || !fileData?.url || !fileData?.headers?.Authorization) {
			throw new Error('Invalid file data provided');
		}

		const tempItemId = uuidv4();
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: fileData.url,
			name: fileData.name,
			collection_name: '',
			status: 'uploading',
			error: '',
			itemId: tempItemId,
			size: 0
		};

		try {
			files = [...files, fileItem];
			console.log('Processing web file with URL:', fileData.url);

			// Configure fetch options with proper headers
			const fetchOptions = {
				headers: {
					Authorization: fileData.headers.Authorization,
					Accept: '*/*'
				},
				method: 'GET'
			};

			// Attempt to fetch the file
			console.log('Fetching file content from Google Drive...');
			const fileResponse = await fetch(fileData.url, fetchOptions);

			if (!fileResponse.ok) {
				const errorText = await fileResponse.text();
				throw new Error(`Failed to fetch file (${fileResponse.status}): ${errorText}`);
			}

			// Get content type from response
			const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';
			console.log('Response received with content-type:', contentType);

			// Convert response to blob
			console.log('Converting response to blob...');
			const fileBlob = await fileResponse.blob();

			if (fileBlob.size === 0) {
				throw new Error('Retrieved file is empty');
			}

			console.log('Blob created:', {
				size: fileBlob.size,
				type: fileBlob.type || contentType
			});

			// Create File object with proper MIME type
			const file = new File([fileBlob], fileData.name, {
				type: fileBlob.type || contentType
			});

			console.log('File object created:', {
				name: file.name,
				size: file.size,
				type: file.type
			});

			if (file.size === 0) {
				throw new Error('Created file is empty');
			}

			// If the file is an audio file, provide the language for STT.
			let metadata = null;
			if (
				(file.type.startsWith('audio/') || file.type.startsWith('video/')) &&
				$settings?.audio?.stt?.language
			) {
				metadata = {
					language: $settings?.audio?.stt?.language
				};
			}

			// Upload file to server
			console.log('Uploading file to server...');
			const uploadedFile = await uploadFile(localStorage.token, file, metadata);

			if (!uploadedFile) {
				throw new Error('Server returned null response for file upload');
			}

			console.log('File uploaded successfully:', uploadedFile);

			// Update file item with upload results
			fileItem.status = 'uploaded';
			fileItem.file = uploadedFile;
			fileItem.id = uploadedFile.id;
			fileItem.size = file.size;
			fileItem.collection_name = uploadedFile?.meta?.collection_name;
			fileItem.url = `${uploadedFile.id}`;

			files = files;
			toast.success($i18n.t('File uploaded successfully'));
		} catch (e) {
			console.error('Error uploading file:', e);
			files = files.filter((f) => f.itemId !== tempItemId);
			toast.error(
				$i18n.t('Error uploading file: {{error}}', {
					error: e.message || 'Unknown error'
				})
			);
		}
	};

	const uploadWeb = async (urls) => {
		if ($user?.role !== 'admin' && !($user?.permissions?.chat?.web_upload ?? true)) {
			toast.error($i18n.t('You do not have permission to upload web content.'));
			return;
		}

		if (!Array.isArray(urls)) {
			urls = [urls];
		}

		// Create file items first
		const fileItems = urls.map((url) => ({
			type: 'text',
			name: url,
			collection_name: '',
			status: 'uploading',
			context: 'full',
			url,
			error: ''
		}));

		// Display all items at once
		files = [...files, ...fileItems];

		for (const fileItem of fileItems) {
			try {
				const res = isYoutubeUrl(fileItem.url)
					? await processYoutubeVideo(localStorage.token, fileItem.url)
					: await processWeb(localStorage.token, '', fileItem.url);

				if (res) {
					fileItem.status = 'uploaded';
					fileItem.collection_name = res.collection_name;
					fileItem.file = {
						...res.file,
						...fileItem.file
					};
				}

				files = [...files];
			} catch (e) {
				files = files.filter((f) => f.name !== url);
				toast.error(`${e}`);
			}
		}
	};

	const onUpload = async (event) => {
		const { type, data } = event;

		if (type === 'google-drive') {
			await uploadGoogleDriveFile(data);
		} else if (type === 'web') {
			await uploadWeb(data);
		}
	};

	const onHistoryChange = (history) => {
		if (history) {
			clearTimeout(contentsRAF);
			contentsRAF = setTimeout(() => {
				getContents();
				contentsRAF = null;
			}, 0);
		} else {
			artifactContents.set([]);
		}
	};

	$: onHistoryChange(history);

	const getContents = () => {
		const messages = history ? createMessagesList(history, history.currentId) : [];
		let contents = [];
		messages.forEach((message) => {
			if (message?.role !== 'user' && message?.content) {
				const { codeBlocks: codeBlocks, htmlGroups: htmlGroups } = getCodeBlockContents(
					message.content
				);

				if (htmlGroups && htmlGroups.length > 0) {
					htmlGroups.forEach((group) => {
						const renderedContent = `
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
							<${''}style>
								body {
									background-color: white; /* Ensure the iframe has a white background */
								}

								${group.css}
							</${''}style>
                        </head>
                        <body>
                            ${group.html}

							<${''}script>
                            	${group.js}
							</${''}script>
                        </body>
                        </html>
                    `;
						contents = [...contents, { type: 'iframe', content: renderedContent }];
					});
				} else {
					// Check for SVG content
					for (const block of codeBlocks) {
						if (block.lang === 'svg' || (block.lang === 'xml' && block.code.includes('<svg'))) {
							contents = [...contents, { type: 'svg', content: block.code }];
						}
					}
				}
			}
		});

		artifactContents.set(contents);
	};

	//////////////////////////
	// Web functions
	//////////////////////////

	const initNewChat = async () => {
		console.log('initNewChat');
		if (HERMES_ONLY_CHAT) {
			await temporaryChatEnabled.set(false);
		} else {
			if ($user?.role !== 'admin' && $user?.permissions?.chat?.temporary_enforced) {
				await temporaryChatEnabled.set(true);
			}

			if ($settings?.temporaryChatByDefault ?? false) {
				if ($temporaryChatEnabled === false) {
					await temporaryChatEnabled.set(true);
				} else if ($temporaryChatEnabled === null) {
					// if set to null set to false; refer to temp chat toggle click handler
					await temporaryChatEnabled.set(false);
				}
			}

			if ($user?.role !== 'admin' && !$user?.permissions?.chat?.temporary) {
				await temporaryChatEnabled.set(false);
			}
		}

		const availableModels = $models
			.filter((m) => !(m?.info?.meta?.hidden ?? false))
			.map((m) => m.id);

		const defaultModels = $config?.default_models ? $config?.default_models.split(',') : [];

		if ($page.url.searchParams.get('models') || $page.url.searchParams.get('model')) {
			const urlModels = (
				$page.url.searchParams.get('models') ||
				$page.url.searchParams.get('model') ||
				''
			)?.split(',');

			if (urlModels.length === 1) {
				if (!$models.find((m) => m.id === urlModels[0])) {
					// Model not found; open model selector and prefill
					const modelSelectorButton = document.getElementById('model-selector-0-button');
					if (modelSelectorButton) {
						modelSelectorButton.click();
						await tick();

						const modelSelectorInput = document.getElementById('model-search-input');
						if (modelSelectorInput) {
							modelSelectorInput.focus();
							modelSelectorInput.value = urlModels[0];
							modelSelectorInput.dispatchEvent(new Event('input'));
						}
					}
				} else {
					// Model found; set it as selected
					selectedModels = urlModels;
				}
			} else {
				// Multiple models; set as selected
				selectedModels = urlModels;
			}

			// Unavailable models filtering
			selectedModels = selectedModels.filter((modelId) =>
				$models.map((m) => m.id).includes(modelId)
			);
		} else {
			if ($selectedFolder?.data?.model_ids) {
				// Set from folder model IDs
				selectedModels = $selectedFolder?.data?.model_ids;
			} else {
				if (sessionStorage.selectedModels) {
					// Set from session storage (temporary selection)
					selectedModels = JSON.parse(sessionStorage.selectedModels);
					sessionStorage.removeItem('selectedModels');
				} else {
					if ($settings?.models) {
						// Set from user settings
						selectedModels = $settings?.models;
					} else if (defaultModels && defaultModels.length > 0) {
						// Set from default models
						selectedModels = defaultModels;
					}
				}
			}

			// Unavailable & hidden models filtering
			selectedModels = selectedModels.filter((modelId) => availableModels.includes(modelId));
		}

		// Ensure at least one model is selected
		if (selectedModels.length === 0 || (selectedModels.length === 1 && selectedModels[0] === '')) {
			if (availableModels.length > 0) {
				if (defaultModels && defaultModels.length > 0) {
					selectedModels = defaultModels.filter((modelId) => availableModels.includes(modelId));
				}

				if (
					selectedModels.length === 0 ||
					(selectedModels.length === 1 && selectedModels[0] === '')
				) {
					// Only fall back to first available model if default models didn't resolve
					selectedModels = [availableModels?.at(0) ?? ''];
				}
			} else {
				selectedModels = [''];
			}
		}

		if ($mobile) {
			await showControls.set(false);
		}
		await showCallOverlay.set(false);
		await showArtifacts.set(false);

		if ($page.url.pathname.includes('/c/')) {
			window.history.replaceState(history.state, '', `/`);
		}

		autoScroll = true;

		resetInput();
		await chatId.set('');
		await chatTitle.set('');

		history = {
			messages: {},
			currentId: null
		};

		chatFiles = [];
		params = {};
		taskIds = null;

		if ($page.url.searchParams.get('youtube')) {
			await uploadWeb(`https://www.youtube.com/watch?v=${$page.url.searchParams.get('youtube')}`);
		}

		if ($page.url.searchParams.get('load-url')) {
			await uploadWeb($page.url.searchParams.get('load-url'));
		}

		if ($page.url.searchParams.get('web-search') === 'true') {
			webSearchEnabled = true;
		}

		if ($page.url.searchParams.get('image-generation') === 'true') {
			imageGenerationEnabled = true;
		}

		if ($page.url.searchParams.get('code-interpreter') === 'true') {
			codeInterpreterEnabled = true;
		}

		if ($page.url.searchParams.get('tools')) {
			selectedToolIds = $page.url.searchParams
				.get('tools')
				?.split(',')
				.map((id) => id.trim())
				.filter((id) => id);
		} else if ($page.url.searchParams.get('tool-ids')) {
			selectedToolIds = $page.url.searchParams
				.get('tool-ids')
				?.split(',')
				.map((id) => id.trim())
				.filter((id) => id);
		}

		// Restore tool selection after OAuth redirect
		const pendingToolId = sessionStorage.getItem('pendingOAuthToolId');
		if (pendingToolId) {
			sessionStorage.removeItem('pendingOAuthToolId');
			if (!selectedToolIds.includes(pendingToolId)) {
				selectedToolIds = [...selectedToolIds, pendingToolId];
			}
		}

		if ($page.url.searchParams.get('call') === 'true') {
			showCallOverlay.set(true);
			showControls.set(true);
		}

		if ($page.url.searchParams.get('q')) {
			const q = $page.url.searchParams.get('q') ?? '';
			messageInput?.setText(q);

			if (q) {
				if (($page.url.searchParams.get('submit') ?? 'true') === 'true') {
					await tick();
					submitPrompt(q);
				}
			}
		}

		selectedModels = normalizeSelectedModels(selectedModels);

		const chatInput = document.getElementById('chat-input');
		setTimeout(() => chatInput?.focus(), 0);
	};

	const loadChat = async () => {
		chatId.set(chatIdProp);

		if ($temporaryChatEnabled) {
			temporaryChatEnabled.set(false);
		}

		chat = await getChatById(localStorage.token, $chatId).catch(async (error) => {
			await goto('/');
			return null;
		});

		if (chat) {
			tags = await getTagsById(localStorage.token, $chatId).catch(async (error) => {
				return [];
			});

			const chatContent = chat.chat;

			if (chatContent) {
				console.log(chatContent);

				selectedModels =
					(chatContent?.models ?? undefined) !== undefined
						? chatContent.models
						: [chatContent.models ?? ''];

				if (!($user?.role === 'admin' || ($user?.permissions?.chat?.multiple_models ?? true))) {
					selectedModels = selectedModels.length > 0 ? [selectedModels[0]] : [''];
				}

				selectedModels = normalizeSelectedModels(selectedModels);

				oldSelectedModelIds = structuredClone(selectedModels);

				history =
					(chatContent?.history ?? undefined) !== undefined
						? chatContent.history
						: convertMessagesToHistory(chatContent.messages);

				chatTitle.set(chatContent.title);

				params = chatContent?.params ?? {};
				chatFiles = chatContent?.files ?? [];

				autoScroll = true;
				await tick();

				if (history.currentId) {
					for (const message of Object.values(history.messages)) {
						if (message && message.role === 'assistant' && message.done !== false) {
							message.done = true;
						}
					}
				}

				const taskRes = await getTaskIdsByChatId(localStorage.token, $chatId).catch((error) => {
					return null;
				});

				if (taskRes) {
					taskIds = taskRes.task_ids;
				}

				await tick();
				await resumePersistedHermesStream(chatIdProp);

				return true;
			} else {
				return null;
			}
		}
	};

	const scrollToBottom = async (behavior = 'auto') => {
		await tick();
		if (messagesContainerElement) {
			messagesContainerElement.scrollTo({
				top: messagesContainerElement.scrollHeight,
				behavior
			});
		}
	};

	let scrollRAF = null;
	let contentsRAF = null;
	const scheduleScrollToBottom = () => {
		if (!scrollRAF) {
			scrollRAF = requestAnimationFrame(async () => {
				scrollRAF = null;
				await scrollToBottom();
			});
		}
	};

	const processNextInQueue = async (targetChatId: string) => {
		const queue = $chatRequestQueues[targetChatId];
		if (!queue || queue.length === 0) return;

		const combinedPrompt = queue.map((m) => m.prompt).join('\n\n');
		const combinedFiles = queue.flatMap((m) => m.files);

		chatRequestQueues.update((q) => {
			const { [targetChatId]: _, ...rest } = q;
			return rest;
		});

		files = combinedFiles;
		await tick();
		await submitPrompt(combinedPrompt);
	};

	const chatCompletedHandler = async (_chatId, modelId, responseMessageId, messages) => {
		const res = await chatCompleted(localStorage.token, {
			model: modelId,
			messages: messages.map((m) => ({
				id: m.id,
				role: m.role,
				content: m.content,
				info: m.info ? m.info : undefined,
				timestamp: m.timestamp,
				...(m.usage ? { usage: m.usage } : {}),
				...(m.sources ? { sources: m.sources } : {})
			})),
			filter_ids: selectedFilterIds.length > 0 ? selectedFilterIds : undefined,
			model_item: $models.find((m) => m.id === modelId),
			chat_id: _chatId,
			session_id: $socket?.id,
			id: responseMessageId
		}).catch((error) => {
			toast.error(`${error}`);
			messages.at(-1).error = { content: error };

			return null;
		});

		if (res !== null && res.messages) {
			// Update chat history with the new messages
			for (const message of res.messages) {
				if (message?.id) {
					// Add null check for message and message.id
					history.messages[message.id] = {
						...history.messages[message.id],
						...(history.messages[message.id].content !== message.content
							? { originalContent: history.messages[message.id].content }
							: {}),
						...message
					};
				}
			}
		}

		await tick();

		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				const persistedChatPayload = await withHermesRuntimeContext({
					models: selectedModels,
					messages: messages,
					history: history,
					params: params,
					files: chatFiles
				});

				chat = await updateChatById(localStorage.token, _chatId, persistedChatPayload);

				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
			}
		}

		taskIds = null;
	};

	const chatActionHandler = async (_chatId, actionId, modelId, responseMessageId, event = null) => {
		const messages = createMessagesList(history, responseMessageId);

		const res = await chatAction(localStorage.token, actionId, {
			model: modelId,
			messages: messages.map((m) => ({
				id: m.id,
				role: m.role,
				content: m.content,
				info: m.info ? m.info : undefined,
				timestamp: m.timestamp,
				...(m.sources ? { sources: m.sources } : {})
			})),
			...(event ? { event: event } : {}),
			model_item: $models.find((m) => m.id === modelId),
			chat_id: _chatId,
			session_id: $socket?.id,
			id: responseMessageId
		}).catch((error) => {
			toast.error(`${error}`);
			messages.at(-1).error = { content: error };
			return null;
		});

		if (res !== null && res.messages) {
			// Update chat history with the new messages
			for (const message of res.messages) {
				history.messages[message.id] = {
					...history.messages[message.id],
					...(history.messages[message.id].content !== message.content
						? { originalContent: history.messages[message.id].content }
						: {}),
					...message
				};
			}
		}

		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				const persistedChatPayload = await withHermesRuntimeContext({
					models: selectedModels,
					messages: messages,
					history: history,
					params: params,
					files: chatFiles
				});

				chat = await updateChatById(localStorage.token, _chatId, persistedChatPayload);

				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
			}
		}
	};

	const getChatEventEmitter = async (modelId: string, chatId: string = '') => {
		return setInterval(() => {
			$socket?.emit('usage', {
				action: 'chat',
				model: modelId,
				chat_id: chatId
			});
		}, 1000);
	};

	const createMessagePair = async (userPrompt) => {
		messageInput?.setText('');

		const normalizedSelectedModels = normalizeSelectedModels(selectedModels);
		if (JSON.stringify(selectedModels) !== JSON.stringify(normalizedSelectedModels)) {
			selectedModels = normalizedSelectedModels;
		}

		if (normalizedSelectedModels.length === 0) {
			toast.error($i18n.t('Model not selected'));
		} else {
			const modelId = normalizedSelectedModels[0];
			const model = $models.filter((m) => m.id === modelId).at(0);

			if (!model) {
				toast.error($i18n.t('Model not found'));
				return;
			}

			const messages = createMessagesList(history, history.currentId);
			const parentMessage = messages.length !== 0 ? messages.at(-1) : null;

			const userMessageId = uuidv4();
			const responseMessageId = uuidv4();

			const userMessage = {
				id: userMessageId,
				parentId: parentMessage ? parentMessage.id : null,
				childrenIds: [responseMessageId],
				role: 'user',
				content: userPrompt ? userPrompt : `[PROMPT] ${userMessageId}`,
				timestamp: Math.floor(Date.now() / 1000)
			};

			const responseMessage = {
				id: responseMessageId,
				parentId: userMessageId,
				childrenIds: [],
				role: 'assistant',
				content: `[RESPONSE] ${responseMessageId}`,
				done: true,

				model: modelId,
				modelName: model.name ?? model.id,
				modelIdx: 0,
				timestamp: Math.floor(Date.now() / 1000)
			};

			if (parentMessage) {
				parentMessage.childrenIds.push(userMessageId);
				history.messages[parentMessage.id] = parentMessage;
			}
			history.messages[userMessageId] = userMessage;
			history.messages[responseMessageId] = responseMessage;

			history.currentId = responseMessageId;

			await tick();

			if (autoScroll) {
				scrollToBottom();
			}

			if (messages.length === 0) {
				await initChatHandler(history);
			} else {
				await saveChatHandler($chatId, history);
			}
		}
	};

	const addMessages = async ({ modelId, parentId, messages }) => {
		const model = $models.filter((m) => m.id === modelId).at(0);

		let parentMessage = history.messages[parentId];
		let currentParentId = parentMessage ? parentMessage.id : null;
		for (const message of messages) {
			let messageId = uuidv4();

			if (message.role === 'user') {
				const userMessage = {
					id: messageId,
					parentId: currentParentId,
					childrenIds: [],
					timestamp: Math.floor(Date.now() / 1000),
					...message
				};

				if (parentMessage) {
					parentMessage.childrenIds.push(messageId);
					history.messages[parentMessage.id] = parentMessage;
				}

				history.messages[messageId] = userMessage;
				parentMessage = userMessage;
				currentParentId = messageId;
			} else {
				const responseMessage = {
					id: messageId,
					parentId: currentParentId,
					childrenIds: [],
					done: true,
					model: model.id,
					modelName: model.name ?? model.id,
					modelIdx: 0,
					timestamp: Math.floor(Date.now() / 1000),
					...message
				};

				if (parentMessage) {
					parentMessage.childrenIds.push(messageId);
					history.messages[parentMessage.id] = parentMessage;
				}

				history.messages[messageId] = responseMessage;
				parentMessage = responseMessage;
				currentParentId = messageId;
			}
		}

		history.currentId = currentParentId;
		await tick();

		if (autoScroll) {
			scrollToBottom();
		}

		if (messages.length === 0) {
			await initChatHandler(history);
		} else {
			await saveChatHandler($chatId, history);
		}
	};

	const chatCompletionEventHandler = async (data, message, chatId) => {
		const { id, done, choices, content, output, sources, selected_model_id, error, usage } = data;

		// Store raw OR-aligned output items from backend
		if (output) {
			message.output = output;
		}

		if (error) {
			await handleOpenAIError(error, message);
		}

		if (sources && !message?.sources) {
			message.sources = sources;
		}

		if (choices) {
			if (choices[0]?.message?.content) {
				// Non-stream response
				message.content += choices[0]?.message?.content;
			} else {
				// Stream response
				let value = choices[0]?.delta?.content ?? '';
				if (message.content == '' && value == '\n') {
					console.log('Empty response');
				} else {
					message.content += value;

					if (navigator.vibrate && ($settings?.hapticFeedback ?? false)) {
						navigator.vibrate(5);
					}

					// Emit chat event for TTS (only when call overlay is active)
					if ($showCallOverlay) {
						const messageContentParts = getMessageContentParts(
							removeAllDetails(message.content),
							$config?.audio?.tts?.split_on ?? 'punctuation'
						);
						messageContentParts.pop();

						// dispatch only last sentence and make sure it hasn't been dispatched before
						if (
							messageContentParts.length > 0 &&
							messageContentParts[messageContentParts.length - 1] !== message.lastSentence
						) {
							message.lastSentence = messageContentParts[messageContentParts.length - 1];
							eventTarget.dispatchEvent(
								new CustomEvent('chat', {
									detail: {
										id: message.id,
										content: messageContentParts[messageContentParts.length - 1]
									}
								})
							);
						}
					}
				}
			}
		}

		if (content) {
			// REALTIME_CHAT_SAVE is disabled
			message.content = content;

			if (navigator.vibrate && ($settings?.hapticFeedback ?? false)) {
				navigator.vibrate(5);
			}

			// Emit chat event for TTS (only when call overlay is active)
			if ($showCallOverlay) {
				const messageContentParts = getMessageContentParts(
					removeAllDetails(message.content),
					$config?.audio?.tts?.split_on ?? 'punctuation'
				);
				messageContentParts.pop();

				// dispatch only last sentence and make sure it hasn't been dispatched before
				if (
					messageContentParts.length > 0 &&
					messageContentParts[messageContentParts.length - 1] !== message.lastSentence
				) {
					message.lastSentence = messageContentParts[messageContentParts.length - 1];
					eventTarget.dispatchEvent(
						new CustomEvent('chat', {
							detail: {
								id: message.id,
								content: messageContentParts[messageContentParts.length - 1]
							}
						})
					);
				}
			}
		}

		if (selected_model_id) {
			message.selectedModelId = selected_model_id;
			message.arena = true;
		}

		if (usage) {
			message.usage = usage;
		}

		history.messages[message.id] = message;

		if (done) {
			message.done = true;

			if ($settings.responseAutoCopy) {
				copyToClipboard(message.content);
			}

			if ($settings.responseAutoPlayback && !$showCallOverlay) {
				await tick();
				document.getElementById(`speak-button-${message.id}`)?.click();
			}

			// Emit chat event for TTS (only when call overlay is active)
			if ($showCallOverlay) {
				let lastMessageContentPart =
					getMessageContentParts(
						removeAllDetails(message.content),
						$config?.audio?.tts?.split_on ?? 'punctuation'
					)?.at(-1) ?? '';
				if (lastMessageContentPart) {
					eventTarget.dispatchEvent(
						new CustomEvent('chat', {
							detail: { id: message.id, content: lastMessageContentPart }
						})
					);
				}
			}
			eventTarget.dispatchEvent(
				new CustomEvent('chat:finish', {
					detail: {
						id: message.id,
						content: message.content
					}
				})
			);

			history.messages[message.id] = message;

			await tick();
			if (autoScroll) {
				scrollToBottom();
			}

			// Fire-and-forget: run chatCompletedHandler for background work
			// (outlet filters, chat save, title gen, follow-ups, tags)
			// without blocking the user from sending new messages.
			chatCompletedHandler(
				chatId,
				message.model,
				message.id,
				createMessagesList(history, message.id)
			);

			// Process next queued request if any
			await processNextInQueue(chatId);
		}

		console.log(data);
		await tick();

		if (autoScroll) {
			scheduleScrollToBottom();
		}
	};

	//////////////////////////
	// Chat functions
	//////////////////////////

	const submitPrompt = async (userPrompt, { _raw = false } = {}) => {
		console.log('submitPrompt', userPrompt, $chatId);

		const _selectedModels = normalizeSelectedModels(selectedModels);

		if (JSON.stringify(selectedModels) !== JSON.stringify(_selectedModels)) {
			selectedModels = _selectedModels;
		}

		let hermesSendContext = getCurrentHermesSessionContext();
		if (!hermesSendContext?.session_id && !$hermesContextLoaded) {
			await loadHermesRuntimeContext();
			hermesSendContext = getCurrentHermesSessionContext();
		}
		const canSendWithHermes =
			!!hermesSendContext?.session_id ||
			canStartNewHermesSessionFromSurface(hermesSendContext, history);

		if (pendingOAuthTools.length > 0) {
			toast.warning($i18n.t('Please connect all required integrations before sending a message'));
			return;
		}
		if (userPrompt === '' && files.length === 0) {
			toast.error($i18n.t('Please enter a prompt'));
			return;
		}
		if (_selectedModels.length === 0 && !canSendWithHermes) {
			toast.error($i18n.t('Model not selected'));
			return;
		}

		if (
			files.length > 0 &&
			files.filter((file) => file.type !== 'image' && file.status === 'uploading').length > 0
		) {
			toast.error(
				$i18n.t(`Oops! There are files still uploading. Please wait for the upload to complete.`)
			);
			return;
		}

		if (
			($config?.file?.max_count ?? null) !== null &&
			files.length + chatFiles.length > $config?.file?.max_count
		) {
			toast.error(
				$i18n.t(`You can only chat with a maximum of {{maxCount}} file(s) at a time.`, {
					maxCount: $config?.file?.max_count
				})
			);
			return;
		}

		// Check if the assistant is still generating the main response
		// (don't block on background tasks like title gen, follow-ups, tags)
		const lastMessage = history.currentId ? history.messages[history.currentId] : null;
		const isGenerating = lastMessage && lastMessage.role === 'assistant' && !lastMessage.done;

		if (isGenerating) {
			if ($settings?.enableMessageQueue ?? true) {
				// Enqueue the request
				const _files = structuredClone(files);
				chatRequestQueues.update((q) => ({
					...q,
					[$chatId]: [...(q[$chatId] ?? []), { id: uuidv4(), prompt: userPrompt, files: _files }]
				}));
				// Clear input
				messageInput?.setText('');
				prompt = '';
				files = [];
				return;
			} else {
				// Interrupt: stop current generation and proceed
				await stopResponse();
				await tick();
			}
		}

		if (history?.currentId) {
			const currentMessage = history.messages[history.currentId];

			if (currentMessage.error && !currentMessage.content) {
				// Error in response
				toast.error($i18n.t(`Oops! There was an error in the previous response.`));
				return;
			}
		}

		messageInput?.setText('');
		prompt = '';

		const messages = createMessagesList(history, history.currentId);
		const _files = structuredClone(files);

		chatFiles.push(
			..._files.filter(
				(item) =>
					['doc', 'text', 'note', 'chat', 'folder', 'collection'].includes(item.type) ||
					(item.type === 'file' && !(item?.content_type ?? '').startsWith('image/'))
			)
		);
		chatFiles = chatFiles.filter(
			// Remove duplicates
			(item, index, array) =>
				array.findIndex((i) => JSON.stringify(i) === JSON.stringify(item)) === index
		);

		files = [];
		messageInput?.setText('');

		// Create user message
		let userMessageId = uuidv4();
		let userMessage = {
			id: userMessageId,
			parentId: messages.length !== 0 ? messages.at(-1).id : null,
			childrenIds: [],
			role: 'user',
			content: userPrompt,
			files: _files.length > 0 ? _files : undefined,
			timestamp: Math.floor(Date.now() / 1000), // Unix epoch
			models: selectedModels
		};

		// Add message to history and Set currentId to messageId
		history.messages[userMessageId] = userMessage;
		history.currentId = userMessageId;

		// Append messageId to childrenIds of parent message
		if (messages.length !== 0) {
			history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
		}

		// focus on chat input
		const chatInput = document.getElementById('chat-input');
		chatInput?.focus();

		saveSessionSelectedModels();

		await sendMessage(history, userMessageId, { newChat: true });
	};

	const sendMessage = async (
		_history,
		parentId: string,
		{
			messages = null,
			modelId = null,
			modelIdx = null,
			newChat = false
		}: {
			messages?: any[] | null;
			modelId?: string | null;
			modelIdx?: number | null;
			newChat?: boolean;
		} = {}
	) => {
		if (autoScroll) {
			scrollToBottom();
		}

		let _chatId = JSON.parse(JSON.stringify($chatId));
		_history = structuredClone(_history);

		const responseMessageIds: Record<PropertyKey, string> = {};
		// If modelId is provided, use it, else use selected model
		let selectedModelIds = modelId
			? [modelId]
			: atSelectedModel !== undefined
				? [atSelectedModel.id]
				: selectedModels;
		const hermesSendContext = getCurrentHermesSessionContext();
		const useHermesTransport =
			!!hermesSendContext?.session_id ||
			canStartNewHermesSessionFromSurface(hermesSendContext, _history);
		const hermesModelId = chat?.chat?.models?.[0] ?? hermesSendContext?.model ?? 'Hermes';

		if (useHermesTransport) {
			selectedModelIds = [hermesModelId];
		}

		// Create response messages for each selected model
		for (const [_modelIdx, modelId] of selectedModelIds.entries()) {
			const model = $models.filter((m) => m.id === modelId).at(0);
			const effectiveModel: any =
				model ??
				(useHermesTransport
					? {
							id: modelId || hermesModelId,
							name: 'Hermes'
						}
					: null);

			if (effectiveModel) {
				let responseMessageId = uuidv4();
				let responseMessage = {
					parentId: parentId,
					id: responseMessageId,
					childrenIds: [],
					role: 'assistant',
					content: '',
					model: effectiveModel.id,
					modelName: useHermesTransport ? 'Hermes' : (effectiveModel.name ?? effectiveModel.id),
					...(useHermesTransport ? { selectedModelId: effectiveModel.id } : {}),
					modelIdx: modelIdx ? modelIdx : _modelIdx,
					...(useHermesTransport
						? {
								done: false,
								hermesStartIntent: !hermesSendContext?.session_id,
								hermesClientRequestId: responseMessageId
							}
						: {}),
					timestamp: Math.floor(Date.now() / 1000) // Unix epoch
				};

				// Add message to history and Set currentId to messageId
				history.messages[responseMessageId] = responseMessage;
				history.currentId = responseMessageId;

				// Append messageId to childrenIds of parent message
				if (parentId !== null && history.messages[parentId]) {
					// Add null check before accessing childrenIds
					history.messages[parentId].childrenIds = [
						...history.messages[parentId].childrenIds,
						responseMessageId
					];
				}

				responseMessageIds[`${modelId}-${modelIdx ? modelIdx : _modelIdx}`] = responseMessageId;
			}
		}
		history = history;
		const isFirstUserTurn = _history.messages[parentId]?.parentId === null;
		_history = structuredClone(history);

		// Create new chat if newChat is true and first user message
		if (newChat && isFirstUserTurn) {
			_chatId = await initChatHandler(_history);
		}

		await tick();

		// Save chat after all messages have been created
		await saveChatHandler(_chatId, _history);

		await Promise.all(
			selectedModelIds.map(async (modelId, _modelIdx) => {
				console.log('modelId', modelId);
				const model = $models.filter((m) => m.id === modelId).at(0);
				const effectiveModel: any =
					model ??
					(useHermesTransport
						? {
								id: modelId || hermesModelId,
								name: 'Hermes'
							}
						: null);

				if (effectiveModel) {
					// If there are image files, check if model is vision capable
					// Skip this check if image generation is enabled, as images may be for editing or are generated outputs in the history
					const hasImages = createMessagesList(_history, parentId).some((message) =>
						message.files?.some(
							(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
						)
					);

					if (
						hasImages &&
						!useHermesTransport &&
						!(effectiveModel.info?.meta?.capabilities?.vision ?? true) &&
						!imageGenerationEnabled
					) {
						toast.error(
							$i18n.t('Model {{modelName}} is not vision capable', {
								modelName: effectiveModel.name ?? effectiveModel.id
							})
						);
					}

					let responseMessageId =
						responseMessageIds[`${modelId}-${modelIdx ? modelIdx : _modelIdx}`];
					const chatEventEmitter = useHermesTransport
						? null
						: await getChatEventEmitter(effectiveModel.id, _chatId);

					scrollToBottom();
					await sendMessageSocket(
						effectiveModel,
						messages && messages.length > 0
							? messages
							: createMessagesList(_history, responseMessageId),
						_history,
						responseMessageId,
						_chatId
					);

					if (chatEventEmitter) clearInterval(chatEventEmitter);
				} else {
					toast.error($i18n.t(`Model {{modelId}} not found`, { modelId }));
				}
			})
		);
	};

	const getFeatures = () => {
		let features = {};

		if ($config?.features)
			features = {
				voice: $showCallOverlay,
				image_generation:
					$config?.features?.enable_image_generation &&
					($user?.role === 'admin' || $user?.permissions?.features?.image_generation)
						? imageGenerationEnabled
						: false,
				code_interpreter:
					$config?.features?.enable_code_interpreter &&
					($user?.role === 'admin' || $user?.permissions?.features?.code_interpreter)
						? codeInterpreterEnabled
						: false,
				web_search:
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
						? webSearchEnabled
						: false
			};

		const currentModels = atSelectedModel?.id ? [atSelectedModel.id] : selectedModels;
		if (
			currentModels.filter(
				(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.web_search ?? true
			).length === currentModels.length
		) {
			if ($config?.features?.enable_web_search && ($settings?.webSearch ?? false) === 'always') {
				features = { ...features, web_search: true };
			}
		}

		if ($settings?.memory ?? false) {
			features = { ...features, memory: true };
		}

		return features;
	};

	const getStopTokens = () => {
		const stop = params?.stop ?? $settings?.params?.stop;
		if (!stop) return undefined;

		const tokens = Array.isArray(stop) ? stop : stop.split(',').map((s) => s.trim());

		return tokens
			.filter(Boolean)
			.map((token) => decodeURIComponent(JSON.parse(`"${token.replace(/"/g, '\\"')}"`)));
	};

	const consumeHermesSessionStream = async ({
		streamId,
		responseMessageId,
		targetChatId,
		hermesSessionContext,
		isResume = false
	}: {
		streamId: string;
		responseMessageId: string;
		targetChatId: string;
		hermesSessionContext: Record<string, any> | null;
		isResume?: boolean;
	}) => {
		const activeTargetId = getHermesTargetId(hermesSessionContext);
		const responseMessage = history.messages[responseMessageId];
		if (!responseMessage) {
			persistHermesActiveStream(targetChatId, activeTargetId, null);
			return false;
		}

		let terminalEvent: 'done' | 'cancel' | 'error' | null = null;
		hermesActiveStreamId = streamId;

		try {
			upsertHermesSessionStatus(responseMessage, {
				description: isResume
					? $i18n.t('Reconnected to Hermes session')
					: $i18n.t('Sending to Hermes session'),
				done: false
			});
			history.messages[responseMessageId] = responseMessage;
			history = history;

			const persistedStream = readPersistedHermesActiveStream(targetChatId, activeTargetId);
			if (isResume && persistedStream?.pendingApproval) {
				attachHermesStreamApproval(
					responseMessageId,
					streamId,
					targetChatId,
					persistedStream.pendingApproval
				);
				history.messages[responseMessageId] = responseMessage;
				history = history;
			}

			await tick();

			const stream = await getHermesSessionMessageStream(localStorage.token, streamId);

			for await (const update of stream) {
				const rawEvent = update?.event ?? 'message';
				const event = normalizeHermesStreamEventName(rawEvent);
				const data = update?.data ?? {};

				if (event === 'token') {
					await chatCompletionEventHandler(
						{
							choices: [
								{
									delta: {
										content: data?.text ?? ''
									}
								}
							]
						},
						responseMessage,
						targetChatId
					);
					continue;
				}

				if (event === 'run.started') {
					upsertHermesSessionStatus(responseMessage, {
						description: isResume
							? $i18n.t('Reconnected to Hermes session')
							: $i18n.t('Sending to Hermes session'),
						done: false
					});
					history.messages[responseMessageId] = responseMessage;
					history = history;
					continue;
				}

				if (event === 'tool') {
					const toolEvent = {
						...data,
						event: typeof rawEvent === 'string' ? rawEvent : (data?.event ?? 'tool')
					};
					appendHermesToolStatus(responseMessage, toolEvent);
					responseMessage.code_executions = upsertHermesToolExecution(
						responseMessage.code_executions,
						toolEvent
					);
					history.messages[responseMessageId] = responseMessage;
					history = history;
					continue;
				}

				if (event === 'approval') {
					upsertHermesSessionStatus(responseMessage, {
						description: $i18n.t('Approval required'),
						done: false
					});
					attachHermesStreamApproval(responseMessageId, streamId, targetChatId, data);
					history.messages[responseMessageId] = responseMessage;
					history = history;
					continue;
				}

				if (event === 'approval.resolved') {
					updatePersistedHermesActiveStream(targetChatId, activeTargetId, {
						pendingApproval: null
					});

					if (responseMessage.hermesApproval) {
						responseMessage.hermesApproval = {
							...responseMessage.hermesApproval,
							state: 'resolved',
							resolution: data?.choice ?? responseMessage.hermesApproval?.resolution ?? 'once',
							interactive: false
						};
						history.messages[responseMessageId] = responseMessage;
						history = history;
					}
					continue;
				}

				if (event === 'approval.error') {
					console.warn('Hermes approval error:', data?.message ?? data);
					continue;
				}

				if (event === 'run.completed') {
					upsertHermesSessionStatus(responseMessage, {
						description: $i18n.t('Hermes session response received'),
						done: true
					});
					history.messages[responseMessageId] = responseMessage;
					history = history;
					continue;
				}

				if (event === 'warning' || event === 'compressed') {
					responseMessage.statusHistory = [
						...(responseMessage.statusHistory ?? []),
						{
							action: `hermes_${event}`,
							description:
								data?.message ??
								(event === 'compressed'
									? $i18n.t('Hermes compressed the session context.')
									: $i18n.t('Hermes reported a warning.')),
							done: true,
							hidden: false,
							query: ''
						}
					];
					history.messages[responseMessageId] = responseMessage;
					history = history;
					continue;
				}

				if (event === 'done') {
					terminalEvent = 'done';
					await finalizeHermesCompletedStream({
						responseMessageId,
						targetChatId,
						hermesSessionContext,
						payload: data
					});
					break;
				}

				if (event === 'cancel') {
					terminalEvent = 'cancel';
					await finalizeHermesInterruptedStream({
						responseMessageId,
						targetChatId,
						description: $i18n.t('Hermes response cancelled')
					});
					await processNextInQueue(targetChatId);
					break;
				}

				if (event === 'apperror') {
					terminalEvent = 'error';
					persistHermesActiveStream(targetChatId, activeTargetId, null);
					throw new Error(data?.message ?? 'Failed to send Hermes session message.');
				}
			}

			if (!terminalEvent) {
				throw new Error('Hermes stream ended unexpectedly.');
			}
		} catch (error) {
			console.error(error);

			if (isResume) {
				await finalizeHermesInterruptedStream({
					responseMessageId,
					targetChatId,
					description: $i18n.t('Hermes stream unavailable'),
					errorMessage: error?.message ?? `${error}`
				});
				history = history;
				return true;
			}

			if (terminalEvent !== 'cancel') {
				toast.error(`${error}`);
			}
			await finalizeHermesInterruptedStream({
				responseMessageId,
				targetChatId,
				description: $i18n.t('Hermes session failed'),
				errorMessage: error?.message ?? `${error}`
			});
			await processNextInQueue(targetChatId);
		} finally {
			if (hermesActiveStreamId === streamId) {
				hermesActiveStreamId = null;
			}
			generating = false;
		}

		await tick();
		scrollToBottom();
		return true;
	};

	const resumePersistedHermesStream = async (targetChatId: string | null | undefined) => {
		if (
			!targetChatId ||
			typeof localStorage === 'undefined' ||
			!localStorage.token ||
			hermesActiveStreamId
		) {
			return;
		}

		const currentTargetId = getCurrentHermesTargetId();
		let persistedStream = readPersistedHermesActiveStream(targetChatId, currentTargetId);
		if (!persistedStream) {
			const recoverableStream = getRecoverableHermesPendingStream();
			if (!recoverableStream) {
				return;
			}

			persistHermesActiveStream(targetChatId, currentTargetId, recoverableStream);
			persistedStream = recoverableStream;
		}

		if (!persistedStream) {
			return;
		}

		const responseMessage = history.messages?.[persistedStream.responseMessageId];
		if (!responseMessage || responseMessage.role !== 'assistant' || responseMessage.done) {
			persistHermesActiveStream(
				targetChatId,
				persistedStream.targetId ?? currentTargetId,
				null
			);
			return;
		}

		let resolvedStreamId = persistedStream.streamId ?? null;
		if (!resolvedStreamId) {
			const userMessage = history.messages?.[responseMessage.parentId];
			const hermesSessionContext = getCurrentHermesSessionContext();
			const resolvedTargetId =
				persistedStream.targetId ?? getCurrentHermesTargetId(hermesSessionContext);

			if (!userMessage?.content && (userMessage?.files?.length ?? 0) === 0) {
				await finalizeHermesInterruptedStream({
					responseMessageId: persistedStream.responseMessageId,
					targetChatId,
					description: $i18n.t('Hermes stream unavailable'),
					errorMessage: $i18n.t('Failed to reattach the pending Hermes request.')
				});
				return;
			}

			const recoveredStream = await startHermesSessionMessageStream(localStorage.token, {
				session_id: persistedStream.sessionId ?? hermesSessionContext?.session_id ?? null,
				message: userMessage.content,
				files: userMessage.files ?? null,
				model:
					(persistedStream.sessionId ?? hermesSessionContext?.session_id)
						? (chat?.chat?.models?.[0] ?? responseMessage.model ?? null)
						: null,
				client_request_id: persistedStream.clientRequestId,
				target_id: resolvedTargetId
			}).catch((error) => {
				console.warn('Failed to reattach pending Hermes start request:', error);
				return null;
			});

			if (!recoveredStream?.stream_id) {
				await finalizeHermesInterruptedStream({
					responseMessageId: persistedStream.responseMessageId,
					targetChatId,
					description: $i18n.t('Hermes stream unavailable'),
					errorMessage: $i18n.t('Failed to reattach the pending Hermes request.')
				});
				return;
			}

			resolvedStreamId = recoveredStream.stream_id;
			updatePersistedHermesActiveStream(targetChatId, resolvedTargetId, {
				streamId: resolvedStreamId,
				sessionId: recoveredStream.session_id ?? persistedStream.sessionId ?? null,
				targetId: recoveredStream.target_id ?? resolvedTargetId
			});
		}

		const streamStatus = await getHermesSessionMessageStreamStatus(
			localStorage.token,
			resolvedStreamId
		).catch((error) => {
			console.warn('Failed to resume persisted Hermes stream:', error);
			return null;
		});

		if (!streamStatus) {
			persistHermesActiveStream(
				targetChatId,
				persistedStream.targetId ?? currentTargetId,
				null
			);
			return;
		}

		if (streamStatus.done) {
			if (streamStatus.status === 'completed' && streamStatus.result) {
				await finalizeHermesCompletedStream({
					responseMessageId: persistedStream.responseMessageId,
					targetChatId,
					hermesSessionContext: getCurrentHermesSessionContext(),
					payload: streamStatus.result
				});
			} else {
				await finalizeHermesInterruptedStream({
					responseMessageId: persistedStream.responseMessageId,
					targetChatId,
					description:
						streamStatus.status === 'cancelled'
							? $i18n.t('Hermes response cancelled')
							: $i18n.t('Hermes session failed'),
					errorMessage:
						streamStatus.status === 'cancelled'
							? null
							: (streamStatus.error ?? $i18n.t('Hermes stream unavailable'))
				});
			}

			await tick();
			scrollToBottom();
			return;
		}

		generating = !streamStatus.done;

		if (streamStatus.status === 'waiting_approval') {
			attachHermesStreamApproval(
				persistedStream.responseMessageId,
				resolvedStreamId,
				targetChatId,
				streamStatus.approval_pending ?? persistedStream.pendingApproval ?? {}
			);
		}

		await consumeHermesSessionStream({
			streamId: resolvedStreamId,
			responseMessageId: persistedStream.responseMessageId,
			targetChatId,
			hermesSessionContext: getCurrentHermesSessionContext(),
			isResume: true
		});
	};

	const sendHermesSessionMessageSocket = async (model, _history, responseMessageId, _chatId) => {
		const responseMessage = _history.messages[responseMessageId];
		const userMessage = _history.messages[responseMessage.parentId];
		const hermesSessionContext = getCurrentHermesSessionContext();
		const targetId = getCurrentHermesTargetId(hermesSessionContext);
		const canSendWithHermes =
			!!hermesSessionContext?.session_id || responseMessage?.hermesStartIntent === true;
		const clientRequestId = responseMessage?.hermesClientRequestId ?? responseMessageId;
		const hasHermesMessagePayload =
			!!userMessage?.content || (userMessage?.files?.length ?? 0) > 0;

		if (!canSendWithHermes || !hasHermesMessagePayload) {
			return false;
		}

		try {
			persistHermesActiveStream(_chatId, targetId, {
				clientRequestId,
				streamId: null,
				responseMessageId,
				sessionId: hermesSessionContext?.session_id ?? null,
				targetId,
				pendingApproval: null,
				updatedAt: Date.now()
			});
			const streamStart = await startHermesSessionMessageStream(localStorage.token, {
				session_id: hermesSessionContext.session_id ?? null,
				message: userMessage.content,
				files: userMessage.files ?? null,
				model: hermesSessionContext.session_id
					? (chat?.chat?.models?.[0] ?? model?.id ?? null)
					: null,
				client_request_id: clientRequestId,
				target_id: targetId
			});
			persistHermesActiveStream(_chatId, targetId, {
				clientRequestId,
				streamId: streamStart.stream_id,
				responseMessageId,
				sessionId: streamStart.session_id,
				targetId: streamStart.target_id ?? targetId,
				pendingApproval: null,
				updatedAt: Date.now()
			});
			generating = true;

			await consumeHermesSessionStream({
				streamId: streamStart.stream_id,
				responseMessageId,
				targetChatId: _chatId,
				hermesSessionContext
			});
		} catch (error) {
			console.error(error);
			toast.error(`${error}`);
			persistHermesActiveStream(_chatId, targetId, null);
			upsertHermesSessionStatus(responseMessage, {
				description: $i18n.t('Hermes session failed'),
				done: true
			});
			responseMessage.error = {
				content: error?.message ?? `${error}`
			};
			responseMessage.done = true;
			history.messages[responseMessageId] = responseMessage;
			history.currentId = responseMessageId;
			await processNextInQueue(_chatId);
		} finally {
			generating = false;
		}

		return true;
	};

	const sendMessageSocket = async (model, _messages, _history, responseMessageId, _chatId) => {
		const responseMessage = _history.messages[responseMessageId];
		const userMessage = _history.messages[responseMessage.parentId];

		if (await sendHermesSessionMessageSocket(model, _history, responseMessageId, _chatId)) {
			return;
		}

		const chatMessageFiles = _messages
			.filter((message) => message.files)
			.flatMap((message) => message.files);

		// Filter chatFiles to only include files that are in the chatMessageFiles
		chatFiles = chatFiles.filter((item) => {
			const fileExists = chatMessageFiles.some((messageFile) => messageFile.id === item.id);
			return fileExists;
		});

		let files = structuredClone(chatFiles);
		files.push(
			...(userMessage?.files ?? []).filter(
				(item) =>
					['doc', 'text', 'note', 'chat', 'collection'].includes(item.type) ||
					(item.type === 'file' && !(item?.content_type ?? '').startsWith('image/'))
			)
		);
		// Remove duplicates
		files = files.filter(
			(item, index, array) =>
				array.findIndex((i) => JSON.stringify(i) === JSON.stringify(item)) === index
		);

		scrollToBottom();
		eventTarget.dispatchEvent(
			new CustomEvent('chat:start', {
				detail: {
					id: responseMessageId
				}
			})
		);
		await tick();

		let userLocation;
		if ($settings?.userLocation) {
			userLocation = await getAndUpdateUserLocation(localStorage.token).catch((err) => {
				console.error(err);
				return undefined;
			});
		}

		const stream =
			model?.info?.params?.stream_response ??
			$settings?.params?.stream_response ??
			params?.stream_response ??
			true;

		let messages = [
			params?.system || $settings.system
				? {
						role: 'system',
						content: `${params?.system ?? $settings?.system ?? ''}`
					}
				: undefined,
			..._messages.map((message) => ({
				...message,
				content: processDetails(message.content),
				// Include output for temp chats (backend will use it and strip before LLM)
				...(message.output ? { output: message.output } : {})
			}))
		].filter((message) => message);

		messages = messages
			.map((message, idx, arr) => {
				const imageFiles = (message?.files ?? []).filter(
					(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
				);

				return {
					role: message.role,
					// Preserve output items so backend can reconstruct tool_calls/tool-role messages (temp chats)
					...(message.output ? { output: message.output } : {}),
					...(message.role === 'user' && imageFiles.length > 0
						? {
								content: [
									{
										type: 'text',
										text: message?.merged?.content ?? message.content
									},
									...imageFiles.map((file) => ({
										type: 'image_url',
										image_url: {
											url: file.url
										}
									}))
								]
							}
						: {
								content: message?.merged?.content ?? message.content
							})
				};
			})
			.filter((message) => message?.role === 'user' || message?.content?.trim());

		const toolIds = [];
		const toolServerIds = [];

		for (const toolId of selectedToolIds) {
			if (toolId.startsWith('direct_server:')) {
				let serverId = toolId.replace('direct_server:', '');
				// Check if serverId is a number
				if (!isNaN(parseInt(serverId))) {
					toolServerIds.push(parseInt(serverId));
				} else {
					toolServerIds.push(serverId);
				}
			} else {
				toolIds.push(toolId);
			}
		}

		// Parse skill mentions (<$skillId|label>) from user messages
		const skillMentionRegex = /<\$([^|>]+)\|?[^>]*>/g;
		const skillIds = [];
		for (const message of messages) {
			const content =
				typeof message.content === 'string' ? message.content : (message.content?.[0]?.text ?? '');
			for (const match of content.matchAll(skillMentionRegex)) {
				if (!skillIds.includes(match[1])) {
					skillIds.push(match[1]);
				}
			}
		}

		// Strip skill mentions from message content
		if (skillIds.length > 0) {
			messages = messages.map((message) => {
				if (typeof message.content === 'string') {
					return {
						...message,
						content: message.content.replace(/<\$[^>]+>/g, '').trim()
					};
				} else if (Array.isArray(message.content)) {
					return {
						...message,
						content: message.content.map((part) =>
							part.type === 'text'
								? { ...part, text: part.text.replace(/<\$[^>]+>/g, '').trim() }
								: part
						)
					};
				}
				return message;
			});
		}

		// Use the user-selected terminal from the dropdown
		const activeTerminalId = $selectedTerminalId ?? null;

		const res = await generateOpenAIChatCompletion(
			localStorage.token,
			{
				stream: stream,
				model: model.id,
				messages: messages,
				params: {
					...$settings?.params,
					...params,
					stop: getStopTokens()
				},

				files: (files?.length ?? 0) > 0 ? files : undefined,

				filter_ids: selectedFilterIds.length > 0 ? selectedFilterIds : undefined,
				tool_ids: toolIds.length > 0 ? toolIds : undefined,
				skill_ids: skillIds.length > 0 ? skillIds : undefined,
				terminal_id: activeTerminalId ?? undefined,
				tool_servers: [
					...($toolServers ?? []).filter(
						(server, idx) => toolServerIds.includes(idx) || toolServerIds.includes(server?.id)
					),
					// Direct terminal servers — always included when enabled (not routed through selectedToolIds)
					...($terminalServers ?? []).filter((t) => !t.id)
				],
				features: getFeatures(),
				variables: {
					...getPromptVariables(
						$user?.name,
						$settings?.userLocation ? userLocation : undefined,
						$user?.email
					)
				},
				model_item: $models.find((m) => m.id === model.id),

				session_id: $socket?.id,
				chat_id: $chatId,
				folder_id: $selectedFolder?.id ?? undefined,

				id: responseMessageId,
				parent_id: userMessage?.id ?? null,
				parent_message: userMessage,

				background_tasks: {
					...(!$temporaryChatEnabled &&
					(messages.length == 1 ||
						(messages.length == 2 &&
							messages.at(0)?.role === 'system' &&
							messages.at(1)?.role === 'user')) &&
					(selectedModels[0] === model.id || atSelectedModel !== undefined)
						? {
								title_generation: $settings?.title?.auto ?? true,
								tags_generation: $settings?.autoTags ?? true
							}
						: {}),
					follow_up_generation: $settings?.autoFollowUps ?? true
				},

				...(stream && (model.info?.meta?.capabilities?.usage ?? false)
					? {
							stream_options: {
								include_usage: true
							}
						}
					: {})
			},
			`${WEBUI_BASE_URL}/api`
		).catch(async (error) => {
			console.log(error);

			let errorMessage = error;
			if (error?.error?.message) {
				errorMessage = error.error.message;
			} else if (error?.message) {
				errorMessage = error.message;
			}

			if (typeof errorMessage === 'object') {
				errorMessage = $i18n.t(`Uh-oh! There was an issue with the response.`);
			}

			toast.error(`${errorMessage}`);
			responseMessage.error = {
				content: error
			};

			responseMessage.done = true;

			history.messages[responseMessageId] = responseMessage;
			history.currentId = responseMessageId;

			return null;
		});

		if (res) {
			if (res.error) {
				await handleOpenAIError(res.error, responseMessage);
			} else {
				if (taskIds) {
					taskIds.push(res.task_id);
				} else {
					taskIds = [res.task_id];
				}
			}
		}

		await tick();
		scrollToBottom();
	};

	const handleOpenAIError = async (error, responseMessage) => {
		let errorMessage = '';
		let innerError;

		if (error) {
			innerError = error;
		}

		console.error(innerError);
		if ('detail' in innerError) {
			// FastAPI error
			toast.error(innerError.detail);
			errorMessage = innerError.detail;
		} else if ('error' in innerError) {
			// OpenAI error
			if ('message' in innerError.error) {
				toast.error(innerError.error.message);
				errorMessage = innerError.error.message;
			} else {
				toast.error(innerError.error);
				errorMessage = innerError.error;
			}
		} else if ('message' in innerError) {
			// OpenAI error
			toast.error(innerError.message);
			errorMessage = innerError.message;
		}

		responseMessage.error = {
			content: $i18n.t(`Uh-oh! There was an issue with the response.`) + '\n' + errorMessage
		};
		responseMessage.done = true;

		if (responseMessage.statusHistory) {
			responseMessage.statusHistory = responseMessage.statusHistory.filter(
				(status) => status.action !== 'knowledge_search'
			);
		}

		history.messages[responseMessage.id] = responseMessage;
	};

	const stopResponse = async () => {
		if (hermesActiveStreamId) {
			await cancelHermesSessionMessageStream(localStorage.token, hermesActiveStreamId).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);
			return;
		}

		if (taskIds) {
			for (const taskId of taskIds) {
				const res = await stopTask(localStorage.token, taskId).catch((error) => {
					toast.error(`${error}`);
					return null;
				});
			}

			taskIds = null;

			const responseMessage = history.messages[history.currentId];
			// Set all response messages to done
			if (responseMessage.parentId && history.messages[responseMessage.parentId]) {
				for (const messageId of history.messages[responseMessage.parentId].childrenIds) {
					history.messages[messageId].done = true;
				}
			}

			history.messages[history.currentId] = responseMessage;

			if (autoScroll) {
				scrollToBottom();
			}
		}

		if (generating) {
			generating = false;
			generationController?.abort();
			generationController = null;
		}

		await processNextInQueue($chatId);
	};

	const submitMessage = async (parentId, prompt) => {
		let userPrompt = prompt;
		let userMessageId = uuidv4();

		let userMessage = {
			id: userMessageId,
			parentId: parentId,
			childrenIds: [],
			role: 'user',
			content: userPrompt,
			models: selectedModels,
			timestamp: Math.floor(Date.now() / 1000) // Unix epoch
		};

		if (parentId !== null) {
			history.messages[parentId].childrenIds = [
				...history.messages[parentId].childrenIds,
				userMessageId
			];
		}

		history.messages[userMessageId] = userMessage;
		history.currentId = userMessageId;

		await tick();

		if (autoScroll) {
			scrollToBottom();
		}

		await sendMessage(history, userMessageId);
	};

	const regenerateResponse = async (message, suggestionPrompt = null) => {
		console.log('regenerateResponse');

		if (history.currentId) {
			let userMessage = history.messages[message.parentId];

			if (!userMessage) {
				toast.error($i18n.t('Parent message not found'));
				return;
			}

			if (autoScroll) {
				scrollToBottom();
			}

			await sendMessage(history, userMessage.id, {
				...(suggestionPrompt
					? {
							messages: [
								...createMessagesList(history, message.id),
								{
									role: 'user',
									content: suggestionPrompt
								}
							]
						}
					: {}),
				...((userMessage?.models ?? [...selectedModels]).length > 1
					? {
							// If multiple models are selected, use the model from the message
							modelId: message.model,
							modelIdx: message.modelIdx
						}
					: {})
			});
		}
	};

	const continueResponse = async () => {
		console.log('continueResponse');
		const _chatId = JSON.parse(JSON.stringify($chatId));

		if (history.currentId && history.messages[history.currentId].done == true) {
			const responseMessage = history.messages[history.currentId];
			responseMessage.done = false;
			await tick();

			const model = $models
				.filter((m) => m.id === (responseMessage?.selectedModelId ?? responseMessage.model))
				.at(0);

			if (model) {
				await sendMessageSocket(
					model,
					createMessagesList(history, responseMessage.id),
					history,
					responseMessage.id,
					_chatId
				);
			}
		}
	};

	const mergeResponses = async (messageId, responses, _chatId) => {
		console.log('mergeResponses', messageId, responses);
		const message = history.messages[messageId];
		const mergedResponse = {
			status: true,
			content: ''
		};
		message.merged = mergedResponse;
		history.messages[messageId] = message;

		try {
			generating = true;
			const [res, controller] = await generateMoACompletion(
				localStorage.token,
				message.model ?? '',
				message.parentId ? history.messages[message.parentId].content : '',
				responses
			);

			if (res && res.ok && res.body && generating) {
				generationController = controller as AbortController;
				const textStream = await createOpenAITextStream(
					res.body,
					Boolean($settings?.splitLargeChunks ?? false)
				);
				for await (const update of textStream) {
					const { value, done, sources, error, usage } = update;
					if (error || done) {
						generating = false;
						generationController = null;
						break;
					}

					if (mergedResponse.content == '' && value == '\n') {
						continue;
					} else {
						mergedResponse.content += value;
						history.messages[messageId] = message;
					}

					if (autoScroll) {
						scheduleScrollToBottom();
					}
				}

				await saveChatHandler(_chatId, history);
			} else {
				console.error(res);
			}
		} catch (e) {
			console.error(e);
		}
	};

	const initChatHandler = async (history) => {
		let _chatId = $chatId;

		if (HERMES_ONLY_CHAT || !$temporaryChatEnabled) {
			const persistedChatPayload = await withHermesRuntimeContext({
				id: _chatId,
				title: $i18n.t('New Chat'),
				models: selectedModels,
				system: $settings.system ?? undefined,
				params: params,
				history: history,
				messages: createMessagesList(history, history.currentId),
				tags: [],
				timestamp: Date.now()
			});

			chat = await createNewChat(localStorage.token, persistedChatPayload, $selectedFolder?.id);

			_chatId = chat.id;
			await chatId.set(_chatId);

			window.history.replaceState(history.state, '', `/c/${_chatId}`);

			await tick();

			await chats.set(await getChatList(localStorage.token, $currentChatPage));
			currentChatPage.set(1);

			selectedFolder.set(null);
		} else {
			_chatId = `local:${$socket?.id}`; // Use socket id for temporary chat
			await chatId.set(_chatId);
		}
		await tick();

		return _chatId;
	};

	const saveChatHandler = async (_chatId, history) => {
		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				const persistedChatPayload = await withHermesRuntimeContext({
					models: selectedModels,
					history: history,
					messages: createMessagesList(history, history.currentId),
					params: params,
					files: chatFiles
				});

				chat = await updateChatById(localStorage.token, _chatId, persistedChatPayload);
			}
		}
	};

	const MAX_DRAFT_LENGTH = 5000;
	let saveDraftTimeout: ReturnType<typeof setTimeout> | null = null;

	const saveDraft = async (draft, chatId = null) => {
		if (saveDraftTimeout) {
			clearTimeout(saveDraftTimeout);
		}

		if (draft.prompt !== null && draft.prompt.length < MAX_DRAFT_LENGTH) {
			saveDraftTimeout = setTimeout(async () => {
				await sessionStorage.setItem(
					`chat-input${chatId ? `-${chatId}` : ''}`,
					JSON.stringify(draft)
				);
			}, 500);
		} else {
			sessionStorage.removeItem(`chat-input${chatId ? `-${chatId}` : ''}`);
		}
	};

	const clearDraft = async (chatId = null) => {
		if (saveDraftTimeout) {
			clearTimeout(saveDraftTimeout);
		}
		await sessionStorage.removeItem(`chat-input${chatId ? `-${chatId}` : ''}`);
	};

	const moveChatHandler = async (chatId, folderId) => {
		if (chatId && folderId) {
			const res = await updateChatFolderIdById(localStorage.token, chatId, folderId).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
				await pinnedChats.set(await getPinnedChatList(localStorage.token));

				toast.success($i18n.t('Chat moved successfully'));
			}
		} else {
			toast.error($i18n.t('Failed to move chat'));
		}
	};

	const archiveChatHandler = async (id: string) => {
		try {
			await archiveChatById(localStorage.token, id);
			currentChatPage.set(1);
			initNewChat();
			await goto('/');
			chats.set(await getChatList(localStorage.token, $currentChatPage));
			pinnedChats.set(await getPinnedChatList(localStorage.token));
			toast.success($i18n.t('Chat archived.'));
		} catch (error) {
			console.error('Error archiving chat:', error);
			toast.error($i18n.t('Failed to archive chat.'));
		}
	};
</script>

<svelte:head>
	<title>
		{$settings.showChatTitleInTab !== false && $chatTitle
			? `${$chatTitle.length > 30 ? `${$chatTitle.slice(0, 30)}...` : $chatTitle} • ${$WEBUI_NAME}`
			: `${$WEBUI_NAME}`}
	</title>
</svelte:head>

<audio id="audioElement" src="" style="display: none;"></audio>

<EventConfirmDialog
	bind:show={showEventConfirmation}
	title={eventConfirmationTitle}
	message={eventConfirmationMessage}
	input={eventConfirmationInput}
	inputPlaceholder={eventConfirmationInputPlaceholder}
	inputValue={eventConfirmationInputValue}
	inputType={eventConfirmationInputType}
	on:confirm={(e) => {
		if (e.detail) {
			eventCallback(e.detail);
		} else {
			eventCallback(true);
		}
	}}
	on:cancel={() => {
		eventCallback(false);
	}}
/>

<div
	class="h-screen max-h-[100dvh] transition-width duration-200 ease-in-out {$showSidebar
		? '  md:max-w-[calc(100%-var(--sidebar-width))]'
		: ' '} w-full max-w-full flex flex-col"
	id="chat-container"
>
	{#if !loading}
		<div in:fade={{ duration: 50 }} class="w-full h-full flex flex-col">
			{#if $selectedFolder && $selectedFolder?.meta?.background_image_url}
				<div
					class="absolute top-0 left-0 w-full h-full bg-cover bg-center bg-no-repeat"
					style="background-image: url({$selectedFolder?.meta?.background_image_url})  "
				/>

				<div
					class="absolute top-0 left-0 w-full h-full bg-linear-to-t from-white to-white/85 dark:from-gray-900 dark:to-gray-900/90 z-0"
				/>
			{:else if $settings?.backgroundImageUrl ?? $config?.license_metadata?.background_image_url ?? null}
				<div
					class="absolute top-0 left-0 w-full h-full bg-cover bg-center bg-no-repeat"
					style="background-image: url({$settings?.backgroundImageUrl ??
						$config?.license_metadata?.background_image_url})  "
				/>

				<div
					class="absolute top-0 left-0 w-full h-full bg-linear-to-t from-white to-white/85 dark:from-gray-900 dark:to-gray-900/90 z-0"
				/>
			{/if}

			<PaneGroup direction="horizontal" class="w-full h-full">
				<Pane defaultSize={50} minSize={30} class="h-full flex relative max-w-full flex-col">
					<FilesOverlay show={dragged} />
					<Navbar
						bind:this={navbarElement}
						chat={{
							id: $chatId,
							chat: {
								title: $chatTitle,
								models: selectedModels,
								system: $settings.system ?? undefined,
								params: params,
								hermesSession: currentHermesSessionContext,
								history: history,
								timestamp: Date.now()
							}
						}}
						chatHermesSession={currentHermesSessionContext}
						chatMeta={chat?.meta ?? null}
						{chatFiles}
						{history}
						title={$chatTitle}
						bind:selectedModels
						showModelSelector={false}
						showControlsButton={false}
						shareEnabled={!!history.currentId}
						{initNewChat}
						{archiveChatHandler}
						{moveChatHandler}
						onSaveTempChat={async () => {
							try {
								if (!history?.currentId || !Object.keys(history.messages).length) {
									toast.error($i18n.t('No conversation to save'));
									return;
								}
								const messages = createMessagesList(history, history.currentId);
								const title =
									messages.find((m) => m.role === 'user')?.content ?? $i18n.t('New Chat');

								const persistedChatPayload = await withHermesRuntimeContext({
									id: uuidv4(),
									title: title.length > 50 ? `${title.slice(0, 50)}...` : title,
									models: selectedModels,
									params: params,
									history: history,
									messages: messages,
									timestamp: Date.now()
								});

								const savedChat = await createNewChat(
									localStorage.token,
									persistedChatPayload,
									null
								);

								if (savedChat) {
									temporaryChatEnabled.set(false);
									chatId.set(savedChat.id);
									chats.set(await getChatList(localStorage.token, $currentChatPage));

									await goto(`/c/${savedChat.id}`);
									toast.success($i18n.t('Conversation saved successfully'));
								}
							} catch (error) {
								console.error('Error saving conversation:', error);
								toast.error($i18n.t('Failed to save conversation'));
							}
						}}
					/>

					<div id="chat-pane" class="flex flex-col flex-auto z-10 w-full @container overflow-auto">
						{#if ($settings?.landingPageMode === 'chat' && !$selectedFolder) || createMessagesList(history, history.currentId).length > 0}
							<div
								class=" pb-2.5 flex flex-col justify-between w-full flex-auto overflow-auto h-0 max-w-full z-10 scrollbar-hidden"
								id="messages-container"
								bind:this={messagesContainerElement}
								on:scroll={(e) => {
									autoScroll =
										messagesContainerElement.scrollHeight - messagesContainerElement.scrollTop <=
										messagesContainerElement.clientHeight + 5;
								}}
							>
								<div class=" h-full w-full flex flex-col">
									<Messages
										chatId={$chatId}
										bind:history
										bind:autoScroll
										bind:prompt
										chatHermesSession={currentHermesSessionContext}
										setInputText={(text) => {
											messageInput?.setText(text);
										}}
										{selectedModels}
										{atSelectedModel}
										{sendMessage}
										{showMessage}
										{submitMessage}
										{continueResponse}
										{regenerateResponse}
										{mergeResponses}
										{chatActionHandler}
										{addMessages}
										{respondToApproval}
										topPadding={true}
										bottomPadding={files.length > 0}
										{onSelect}
									/>
								</div>
							</div>

							<div class=" pb-2 {dragged ? 'z-0' : 'z-10'}">
								{#if composerActivityMessage}
									<div in:fade={{ duration: 120 }} class="px-0.5 pb-2">
										<HermesComposerActivityStrip
											message={composerActivityMessage}
											statusUpdatesEnabled={getMessageStatusUpdatesEnabled(composerActivityMessage)}
										/>
									</div>
								{/if}

								{#if composerPendingApproval && composerPendingApprovalMessageId}
									<div in:fade={{ duration: 120 }} class="px-0.5 pb-2">
										<HermesApprovalCard
											embedded={true}
											approval={composerPendingApproval}
											disabled={!(composerPendingApproval?.interactive ?? false)}
											onResolve={(resolution) => {
												respondToApproval(composerPendingApprovalMessageId, resolution);
											}}
										/>
									</div>
								{/if}

								<MessageInput
									bind:this={messageInput}
									hermesMode={true}
									{history}
									{taskIds}
									{selectedModels}
									bind:files
									bind:prompt
									bind:autoScroll
									bind:selectedToolIds
									bind:selectedFilterIds
									bind:imageGenerationEnabled
									bind:codeInterpreterEnabled
									{pendingOAuthTools}
									bind:webSearchEnabled
									bind:atSelectedModel
									bind:showCommands
									bind:dragged
									toolServers={$toolServers}
									{generating}
									{stopResponse}
									{createMessagePair}
									{onUpload}
									messageQueue={$chatRequestQueues[$chatId] ?? []}
									onQueueSendNow={async (id) => {
										const queue = $chatRequestQueues[$chatId] ?? [];
										const item = queue.find((m) => m.id === id);
										if (item) {
											// Remove from queue
											chatRequestQueues.update((q) => ({
												...q,
												[$chatId]: queue.filter((m) => m.id !== id)
											}));
											// Stop current generation first
											await stopResponse();
											await tick();
											// Set files and submit
											files = item.files;
											await tick();
											await submitPrompt(item.prompt);
										}
									}}
									onQueueEdit={(id) => {
										const queue = $chatRequestQueues[$chatId] ?? [];
										const item = queue.find((m) => m.id === id);
										if (item) {
											// Remove from queue
											chatRequestQueues.update((q) => ({
												...q,
												[$chatId]: queue.filter((m) => m.id !== id)
											}));
											// Set files and restore prompt to input
											files = item.files;
											messageInput?.setText(item.prompt);
										}
									}}
									onQueueDelete={(id) => {
										const queue = $chatRequestQueues[$chatId] ?? [];
										chatRequestQueues.update((q) => ({
											...q,
											[$chatId]: queue.filter((m) => m.id !== id)
										}));
									}}
									onChange={(data) => {
										if (!$temporaryChatEnabled) {
											saveDraft(data, $chatId);
										}
									}}
									on:submit={async (e) => {
										clearDraft();
										if (e.detail || files.length > 0) {
											await tick();

											submitPrompt(e.detail.replaceAll('\n\n', '\n'));
										}
									}}
								/>

								<div
									class="absolute bottom-1 text-xs text-gray-500 text-center line-clamp-1 right-0 left-0"
								>
									<!-- {$i18n.t('LLMs can make mistakes. Verify important information.')} -->
								</div>
							</div>
						{:else}
							<div class="flex items-center h-full">
								<Placeholder
									{history}
									{selectedModels}
									bind:messageInput
									bind:files
									bind:prompt
									bind:autoScroll
									bind:selectedToolIds
									bind:selectedFilterIds
									bind:imageGenerationEnabled
									bind:codeInterpreterEnabled
									bind:webSearchEnabled
									bind:atSelectedModel
									bind:showCommands
									bind:dragged
									{pendingOAuthTools}
									toolServers={$toolServers}
									{stopResponse}
									{createMessagePair}
									{onSelect}
									{onUpload}
									onChange={(data) => {
										if (!$temporaryChatEnabled) {
											saveDraft(data);
										}
									}}
									on:submit={async (e) => {
										clearDraft();
										if (e.detail || files.length > 0) {
											await tick();
											submitPrompt(e.detail.replaceAll('\n\n', '\n'));
										}
									}}
								/>
							</div>
						{/if}
					</div>
				</Pane>

				<ChatControls
					bind:this={controlPaneComponent}
					bind:history
					bind:chatFiles
					bind:params
					bind:files
					bind:pane={controlPane}
					chatId={$chatId}
					chatHermesSession={currentHermesSessionContext}
					chatMeta={chat?.meta ?? null}
					modelId={selectedModelIds?.at(0) ?? null}
					models={selectedModelIds.reduce((a, e, i, arr) => {
						const model = $models.find((m) => m.id === e);
						if (model) {
							return [...a, model];
						}
						return a;
					}, [])}
					{submitPrompt}
					{stopResponse}
					{showMessage}
					{taskIds}
					hermesStreamActive={!!hermesActiveStreamId || hasPersistedHermesActiveStream}
					{eventTarget}
					{codeInterpreterEnabled}
					onHermesProfileSwitched={handleHermesProfileSwitched}
				/>
			</PaneGroup>
		</div>
	{:else if loading}
		<div class=" flex items-center justify-center h-full w-full">
			<div class="m-auto">
				<Spinner className="size-5" />
			</div>
		</div>
	{/if}
</div>

<style>
	::-webkit-scrollbar {
		height: 0.5rem;
		width: 0.5rem;
	}
</style>
