export type HermesWorkspaceTreeEntry = string | HermesWorkspaceTreeItem;

export type HermesWorkspaceTreeItem = {
	path?: string | null;
	name?: string | null;
	label?: string | null;
	type?: 'file' | 'directory' | null;
	size?: number | null;
	modified?: number | null;
};

export type HermesWorkspaceTreeNode = {
	path: string;
	name: string;
	type: 'file' | 'directory';
	depth: number;
	size?: number | null;
	modified?: number | null;
	children: HermesWorkspaceTreeNode[];
	source?: HermesWorkspaceTreeItem | string;
};

const normalizeSegment = (segment: string) => segment.trim().replace(/^\.\/+/, '').replace(/^\/+|\/+$/g, '');

export const normalizeHermesWorkspaceTreePath = (path: string | null | undefined) => {
	if (!path) {
		return '';
	}

	const normalized = path.replaceAll('\\', '/').replace(/\/+/g, '/').trim();

	if (!normalized) {
		return '';
	}

	if (normalized === '/') {
		return '/';
	}

	return normalized.replace(/\/+$/, '');
};

export const getHermesWorkspaceTreeLeafName = (path: string | null | undefined) => {
	const normalizedPath = normalizeHermesWorkspaceTreePath(path);

	if (!normalizedPath) {
		return '';
	}

	if (normalizedPath === '/') {
		return '/';
	}

	return normalizedPath.split('/').filter(Boolean).at(-1) ?? '';
};

export const getHermesWorkspaceTreeParentPath = (path: string | null | undefined) => {
	const normalizedPath = normalizeHermesWorkspaceTreePath(path);

	if (!normalizedPath || normalizedPath === '/') {
		return '';
	}

	const lastSlashIndex = normalizedPath.lastIndexOf('/');

	if (lastSlashIndex <= 0) {
		return normalizedPath.startsWith('/') ? '/' : '';
	}

	return normalizedPath.slice(0, lastSlashIndex);
};

export const getHermesWorkspaceTreeAncestorPaths = (
	path: string | null | undefined,
	rootPath: string | null | undefined = ''
) => {
	const normalizedPath = normalizeHermesWorkspaceTreePath(path);
	const normalizedRootPath = normalizeHermesWorkspaceTreePath(rootPath);

	if (!normalizedPath || normalizedPath === '/') {
		return normalizedRootPath ? [normalizedRootPath] : [];
	}

	const ancestors: string[] = [];
	let currentPath = getHermesWorkspaceTreeParentPath(normalizedPath);

	while (currentPath) {
		if (
			normalizedRootPath &&
			currentPath !== normalizedRootPath &&
			!currentPath.startsWith(`${normalizedRootPath}/`)
		) {
			break;
		}

		ancestors.unshift(currentPath);

		if (normalizedRootPath && currentPath === normalizedRootPath) {
			break;
		}

		currentPath = getHermesWorkspaceTreeParentPath(currentPath);
	}

	return ancestors;
};

const getHermesWorkspaceTreeDepth = (path: string) =>
	normalizeHermesWorkspaceTreePath(path)
		.split('/')
		.filter(Boolean).length;

const getHermesWorkspaceTreeName = (path: string) => getHermesWorkspaceTreeLeafName(path) || path;

const joinHermesWorkspaceTreePath = (basePath: string, name: string) => {
	const normalizedBasePath = normalizeHermesWorkspaceTreePath(basePath);
	const normalizedName = normalizeSegment(name);

	if (!normalizedName) {
		return normalizedBasePath;
	}

	if (!normalizedBasePath) {
		return normalizedName;
	}

	if (normalizedBasePath === '/') {
		return `/${normalizedName}`;
	}

	return `${normalizedBasePath}/${normalizedName}`;
};

const normalizeHermesWorkspaceTreeItem = (
	item: HermesWorkspaceTreeEntry,
	basePath: string
): {
	path: string;
	typeHint: 'file' | 'directory' | null;
	size?: number | null;
	modified?: number | null;
	source: HermesWorkspaceTreeItem | string;
} | null => {
	if (typeof item === 'string') {
		const normalizedPath = normalizeHermesWorkspaceTreePath(item);

		return normalizedPath
			? {
					path: normalizedPath,
					typeHint: item.trim().endsWith('/') ? 'directory' : null,
					source: item
				}
			: null;
	}

	const rawPath = normalizeHermesWorkspaceTreePath(item.path ?? item.label ?? item.name ?? '');
	const resolvedPath = rawPath
		? rawPath
		: normalizeHermesWorkspaceTreePath(joinHermesWorkspaceTreePath(basePath, item.label ?? item.name ?? ''));

	if (!resolvedPath) {
		return null;
	}

	const typeHint =
		item.type ??
		((item.path ?? item.label ?? item.name ?? '').trim().endsWith('/') ? 'directory' : null);

	return {
		path: resolvedPath,
		typeHint,
		size: item.size ?? null,
		modified: item.modified ?? null,
		source: item
	};
};

const sortHermesWorkspaceTreeNodes = (nodes: HermesWorkspaceTreeNode[]) => {
	nodes.sort((left, right) => {
		if (left.type !== right.type) {
			return left.type === 'directory' ? -1 : 1;
		}

		return left.name.localeCompare(right.name);
	});

	for (const node of nodes) {
		if (node.children.length > 0) {
			sortHermesWorkspaceTreeNodes(node.children);
		}
	}
};

export const buildHermesWorkspaceTree = (
	entries: HermesWorkspaceTreeEntry[] = [],
	basePath = ''
): HermesWorkspaceTreeNode[] => {
	const normalizedBasePath = normalizeHermesWorkspaceTreePath(basePath);
	const normalizedItems = entries
		.map((item) => normalizeHermesWorkspaceTreeItem(item, normalizedBasePath))
		.filter((item): item is NonNullable<typeof item> => !!item);

	const explicitKinds = new Map<string, 'file' | 'directory'>();
	const ancestorPaths = new Set<string>();
	const metadataByPath = new Map<
		string,
		{
			size?: number | null;
			modified?: number | null;
			source: HermesWorkspaceTreeItem | string;
		}
	>();
	const requiredPaths = new Set<string>();

	for (const item of normalizedItems) {
		requiredPaths.add(item.path);
		if (item.typeHint) {
			explicitKinds.set(item.path, item.typeHint);
		}
		metadataByPath.set(item.path, {
			size: item.size ?? null,
			modified: item.modified ?? null,
			source: item.source
		});

		for (const ancestorPath of getHermesWorkspaceTreeAncestorPaths(
			item.path,
			normalizedBasePath
		)) {
			requiredPaths.add(ancestorPath);
			ancestorPaths.add(ancestorPath);
		}
	}

	if (normalizedBasePath) {
		requiredPaths.add(normalizedBasePath);
		ancestorPaths.add(normalizedBasePath);
	}

	const sortedPaths = [...requiredPaths].sort(
		(left, right) => getHermesWorkspaceTreeDepth(left) - getHermesWorkspaceTreeDepth(right) || left.localeCompare(right)
	);
	const nodeByPath = new Map<string, HermesWorkspaceTreeNode>();

	for (const path of sortedPaths) {
		const parentPath = getHermesWorkspaceTreeParentPath(path);
		const nodeType = ancestorPaths.has(path) ? 'directory' : (explicitKinds.get(path) ?? 'file');
		const name = getHermesWorkspaceTreeName(path);
		const metadata = metadataByPath.get(path);
		const node: HermesWorkspaceTreeNode = {
			path,
			name,
			type: nodeType,
			depth: getHermesWorkspaceTreeDepth(path),
			size: metadata?.size ?? null,
			modified: metadata?.modified ?? null,
			children: [],
			source: metadata?.source
		};

		nodeByPath.set(path, node);

		if (parentPath && nodeByPath.has(parentPath)) {
			nodeByPath.get(parentPath)?.children.push(node);
		}
	}

	const rootNodes = sortedPaths
		.map((path) => nodeByPath.get(path))
		.filter(
			(node): node is HermesWorkspaceTreeNode =>
				!!node &&
				(!getHermesWorkspaceTreeParentPath(node.path) ||
					!nodeByPath.has(getHermesWorkspaceTreeParentPath(node.path)))
		);

	sortHermesWorkspaceTreeNodes(rootNodes);

	return rootNodes;
};
