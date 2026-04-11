import { isCodeFile } from './codeHighlight';

export type HermesGeneratedWorkspaceFile = {
	name: string;
	url: string;
	executionName?: string;
	messageId?: string;
};

export type HermesWorkspaceSurfaceItem = {
	id: string;
	name: string;
	source: 'chat' | 'generated' | 'workspace';
	type: string;
	reference: string;
	content?: string | null;
	fileId?: string | null;
	url?: string | null;
	contentType?: string | null;
	size?: number | null;
	executionName?: string;
	messageId?: string;
	previewable: boolean;
};

export type HermesWorkspaceSurfaceSummary = {
	totalCount: number;
	workspaceCount: number;
	generatedCount: number;
	chatCount: number;
};

export type HermesLinkedWorkspaceSummary = {
	totalLinked: number;
	generated: number;
	attached: number;
};

export type HermesWorkspacePreviewMode =
	| 'image'
	| 'video'
	| 'audio'
	| 'pdf'
	| 'sqlite'
	| 'office'
	| 'text'
	| 'unsupported';

const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico', 'avif']);
const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov', 'ogv', 'avi', 'mkv']);
const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'oga', 'flac', 'm4a', 'aac', 'wma', 'opus']);
const SQLITE_EXTS = new Set(['db', 'sqlite', 'sqlite3', 'db3']);
const OFFICE_EXTS = new Set(['docx', 'xlsx', 'pptx']);
const TEXT_EXTS = new Set([
	'md',
	'markdown',
	'mdx',
	'csv',
	'tsv',
	'html',
	'htm',
	'json',
	'jsonc',
	'jsonl',
	'json5',
	'svg',
	'ipynb',
	'txt',
	'log',
	'xml',
	'yaml',
	'yml'
]);

const getExt = (name: string | null | undefined) => name?.split('.').pop()?.toLowerCase() ?? '';

export const getHermesWorkspaceSurfaceSourceLabel = (
	source: HermesWorkspaceSurfaceItem['source']
) => {
	if (source === 'generated') {
		return 'Generated in this chat';
	}

	if (source === 'chat') {
		return 'Attached to this chat';
	}

	return 'Workspace file';
};

export const getHermesWorkspaceSurfaceItemLabel = (item: HermesWorkspaceSurfaceItem) => {
	if (item.source === 'generated') {
		return 'Generated in this chat';
	}

	if (item.source === 'workspace') {
		return 'Workspace file';
	}

	return item.fileId ? 'Attached to this chat' : 'Chat note';
};

export const summarizeHermesWorkspaceSurfaceItems = (
	items: HermesWorkspaceSurfaceItem[] = []
): HermesWorkspaceSurfaceSummary => {
	return items.reduce(
		(summary, item) => {
			summary.totalCount += 1;

			if (item.source === 'generated') {
				summary.generatedCount += 1;
			} else if (item.source === 'workspace') {
				summary.workspaceCount += 1;
			} else {
				summary.chatCount += 1;
			}

			return summary;
		},
		{
			totalCount: 0,
			workspaceCount: 0,
			generatedCount: 0,
			chatCount: 0
		}
	);
};

export const buildHermesLinkedWorkspaceSummary = (
	chatFiles: any[] = [],
	generatedFiles: HermesGeneratedWorkspaceFile[] = []
): HermesLinkedWorkspaceSummary => {
	const generated = Array.isArray(generatedFiles) ? generatedFiles.length : 0;
	const attached = Array.isArray(chatFiles) ? chatFiles.length : 0;

	return {
		totalLinked: generated + attached,
		generated,
		attached
	};
};

export const getHermesWorkspacePreviewMode = (
	name: string,
	contentType?: string | null
): HermesWorkspacePreviewMode => {
	const ext = getExt(name);
	const normalizedContentType = (contentType ?? '').toLowerCase();

	if (normalizedContentType.startsWith('image/') || IMAGE_EXTS.has(ext)) {
		return 'image';
	}

	if (normalizedContentType.startsWith('video/') || VIDEO_EXTS.has(ext)) {
		return 'video';
	}

	if (normalizedContentType.startsWith('audio/') || AUDIO_EXTS.has(ext)) {
		return 'audio';
	}

	if (normalizedContentType === 'application/pdf' || ext === 'pdf') {
		return 'pdf';
	}

	if (SQLITE_EXTS.has(ext)) {
		return 'sqlite';
	}

	if (
		normalizedContentType ===
			'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
		normalizedContentType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
		normalizedContentType ===
			'application/vnd.openxmlformats-officedocument.presentationml.presentation' ||
		OFFICE_EXTS.has(ext)
	) {
		return 'office';
	}

	if (
		normalizedContentType.startsWith('text/') ||
		normalizedContentType.includes('json') ||
		normalizedContentType.includes('xml') ||
		normalizedContentType.includes('markdown') ||
		TEXT_EXTS.has(ext) ||
		isCodeFile(name)
	) {
		return 'text';
	}

	return 'unsupported';
};

export const buildHermesWorkspaceSurfaceItems = (
	chatFiles: any[] = [],
	generatedFiles: HermesGeneratedWorkspaceFile[] = []
): HermesWorkspaceSurfaceItem[] => {
	const chatItems = (Array.isArray(chatFiles) ? chatFiles : [])
		.map((file, index) => {
			const name = file?.name ?? file?.filename ?? '';
			const type = typeof file?.type === 'string' ? file.type : 'file';
			const fileId =
				typeof file?.id === 'string'
					? file.id
					: typeof file?.file?.id === 'string'
						? file.file.id
						: null;
			const url = typeof file?.url === 'string' ? file.url : null;
			const contentType =
				typeof file?.content_type === 'string'
					? file.content_type
					: typeof file?.meta?.content_type === 'string'
						? file.meta.content_type
						: typeof file?.file?.meta?.content_type === 'string'
							? file.file.meta.content_type
							: null;
			const reference =
				typeof file?.meta?.path === 'string' && file.meta.path ? file.meta.path : url || name;
			const previewable =
				typeof file?.content === 'string' || (type === 'file' && !!fileId) || (type === 'file' && !!url);

			return {
				id: `chat:${fileId ?? url ?? name ?? index}:${index}`,
				name,
				source: 'chat' as const,
				type,
				reference,
				content: typeof file?.content === 'string' ? file.content : null,
				fileId,
				url,
				contentType,
				size: typeof file?.size === 'number' ? file.size : (file?.meta?.size ?? null),
				previewable
			};
		})
		.filter((item) => item.name);

	const generatedItems = (Array.isArray(generatedFiles) ? generatedFiles : [])
		.filter(
			(file): file is HermesGeneratedWorkspaceFile =>
				!!file &&
				typeof file.name === 'string' &&
				!!file.name &&
				typeof file.url === 'string' &&
				!!file.url
		)
		.map((file, index) => ({
			id: `generated:${file.url}:${index}`,
			name: file.name,
			source: 'generated' as const,
			type: 'file',
			reference: file.url,
			url: file.url,
			executionName: file.executionName,
			messageId: file.messageId,
			previewable: true
		}));

	return [...generatedItems, ...chatItems];
};

export const getValidHermesGeneratedFiles = (files: unknown): HermesGeneratedWorkspaceFile[] => {
	if (!Array.isArray(files)) {
		return [];
	}

	return files
		.map((file: any) => ({
			name: typeof file?.name === 'string' ? file.name : '',
			url: typeof file?.url === 'string' ? file.url : ''
		}))
	.filter((file) => file.name && file.url);
};

const getCurrentBranchMessages = (history: {
	currentId?: string | null;
	messages?: Record<string, any>;
}) => {
	const messages = history?.messages ?? {};
	const branchMessages: any[] = [];
	const seen = new Set<string>();

	let messageId = history?.currentId ?? null;

	while (messageId && !seen.has(messageId)) {
		const message = messages[messageId];
		if (!message) {
			break;
		}

		branchMessages.push(message);
		seen.add(messageId);
		messageId = message.parentId ?? null;
	}

	return branchMessages;
};

export const collectHermesGeneratedWorkspaceFiles = (history: {
	currentId?: string | null;
	messages?: Record<string, any>;
}): HermesGeneratedWorkspaceFile[] => {
	const generatedFiles: HermesGeneratedWorkspaceFile[] = [];
	const seenFiles = new Set<string>();

	for (const message of getCurrentBranchMessages(history)) {
		const executions = Array.isArray(message?.code_executions) ? message.code_executions : [];

		for (let executionIndex = executions.length - 1; executionIndex >= 0; executionIndex -= 1) {
			const execution = executions[executionIndex];
			const files = getValidHermesGeneratedFiles(execution?.result?.files);

			for (let fileIndex = files.length - 1; fileIndex >= 0; fileIndex -= 1) {
				const file = files[fileIndex];
				const { name, url } = file;

				const fileKey = `${url}::${name}`;
				if (seenFiles.has(fileKey)) {
					continue;
				}

				seenFiles.add(fileKey);
				generatedFiles.push({
					name,
					url,
					executionName: execution?.name ?? '',
					messageId: message?.id ?? undefined
				});
			}
		}
	}

	return generatedFiles;
};
