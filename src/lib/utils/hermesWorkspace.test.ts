import { describe, expect, test } from 'vitest';

import {
	buildHermesLinkedWorkspaceSummary,
	buildHermesWorkspaceSurfaceItems,
	collectHermesGeneratedWorkspaceFiles,
	getHermesWorkspacePreviewMode,
	getValidHermesGeneratedFiles
} from './hermesWorkspace';

describe('collectHermesGeneratedWorkspaceFiles', () => {
	test('filters generated file entries to valid workspace files', () => {
		expect(
			getValidHermesGeneratedFiles([
				{ name: 'chart.png', url: '/files/chart.png' },
				{ name: '', url: '/files/empty-name.png' },
				{ name: 'missing-url.png' },
				{ url: '/files/missing-name.png' },
				null
			])
		).toEqual([
			{
				name: 'chart.png',
				url: '/files/chart.png'
			}
		]);
	});

	test('collects generated files from the current branch in latest-first order', () => {
		const history = {
			currentId: 'assistant2',
			messages: {
				root: { id: 'root', parentId: null },
				user1: { id: 'user1', parentId: 'root' },
				assistant1: {
					id: 'assistant1',
					parentId: 'user1',
					code_executions: [
						{
							name: 'build-report',
							result: {
								files: [{ name: 'report.csv', url: '/files/report.csv' }]
							}
						}
					]
				},
				user2: { id: 'user2', parentId: 'assistant1' },
				assistant2: {
					id: 'assistant2',
					parentId: 'user2',
					code_executions: [
						{
							name: 'generate-chart',
							result: {
								files: [
									{ name: 'chart.png', url: '/files/chart.png' },
									{ name: 'report.csv', url: '/files/report.csv' }
								]
							}
						}
					]
				},
				sideUser: { id: 'sideUser', parentId: 'assistant1' },
				sideAssistant: {
					id: 'sideAssistant',
					parentId: 'sideUser',
					code_executions: [
						{
							name: 'side-branch-run',
							result: {
								files: [{ name: 'ignore.txt', url: '/files/ignore.txt' }]
							}
						}
					]
				}
			}
		};

		expect(collectHermesGeneratedWorkspaceFiles(history)).toEqual([
			{
				name: 'report.csv',
				url: '/files/report.csv',
				executionName: 'generate-chart',
				messageId: 'assistant2'
			},
			{
				name: 'chart.png',
				url: '/files/chart.png',
				executionName: 'generate-chart',
				messageId: 'assistant2'
			}
		]);
	});

	test('ignores malformed file entries and messages without executions', () => {
		const history = {
			currentId: 'assistant1',
			messages: {
				root: { id: 'root', parentId: null },
				assistant1: {
					id: 'assistant1',
					parentId: 'root',
					code_executions: [
						{
							name: 'cleanup',
							result: {
								files: [
									{ name: 'valid.log', url: '/files/valid.log' },
									{ name: '', url: '/files/empty-name.log' },
									{ name: 'missing-url.log' }
								]
							}
						},
						{ name: 'no-files', result: {} }
					]
				}
			}
		};

		expect(collectHermesGeneratedWorkspaceFiles(history)).toEqual([
			{
				name: 'valid.log',
				url: '/files/valid.log',
				executionName: 'cleanup',
				messageId: 'assistant1'
			}
		]);
	});
});

describe('buildHermesWorkspaceSurfaceItems', () => {
	test('normalizes generated and chat-backed files into a single surface list', () => {
		expect(
			buildHermesWorkspaceSurfaceItems(
				[
					{
						id: 'file-1',
						type: 'file',
						name: 'brief.md',
						url: 'file-1',
						content_type: 'text/markdown',
						size: 128
					},
					{
						type: 'doc',
						name: 'Spec excerpt',
						content: 'Short note'
					}
				],
				[{ name: 'chart.png', url: '/artifacts/chart.png', executionName: 'plot' }]
			)
		).toEqual([
			{
				id: 'generated:/artifacts/chart.png:0',
				name: 'chart.png',
				source: 'generated',
				type: 'file',
				reference: '/artifacts/chart.png',
				url: '/artifacts/chart.png',
				executionName: 'plot',
				messageId: undefined,
				previewable: true
			},
			{
				id: 'chat:file-1:0',
				name: 'brief.md',
				source: 'chat',
				type: 'file',
				reference: 'file-1',
				content: null,
				fileId: 'file-1',
				url: 'file-1',
				contentType: 'text/markdown',
				size: 128,
				previewable: true
			},
			{
				id: 'chat:Spec excerpt:1',
				name: 'Spec excerpt',
				source: 'chat',
				type: 'doc',
				reference: 'Spec excerpt',
				content: 'Short note',
				fileId: null,
				url: null,
				contentType: null,
				size: null,
				previewable: true
			}
		]);
	});
});

describe('buildHermesLinkedWorkspaceSummary', () => {
	test('counts attached and generated files without inventing extra scope', () => {
		expect(
			buildHermesLinkedWorkspaceSummary(
				[
					{ id: 'file-1', name: 'brief.md' },
					{ id: 'file-2', name: 'chart.png' }
				],
				[{ name: 'result.csv', url: '/files/result.csv' }]
			)
		).toEqual({
			totalLinked: 3,
			generated: 1,
			attached: 2
		});
	});

	test('treats missing collections as an empty continuity snapshot', () => {
		expect(buildHermesLinkedWorkspaceSummary(null as any, undefined as any)).toEqual({
			totalLinked: 0,
			generated: 0,
			attached: 0
		});
	});
});

describe('getHermesWorkspacePreviewMode', () => {
	test('detects binary preview types from content type and extension', () => {
		expect(getHermesWorkspacePreviewMode('plot.png', 'image/png')).toBe('image');
		expect(getHermesWorkspacePreviewMode('recording.mp3', 'audio/mpeg')).toBe('audio');
		expect(getHermesWorkspacePreviewMode('deck.pptx')).toBe('office');
		expect(getHermesWorkspacePreviewMode('archive.sqlite3')).toBe('sqlite');
		expect(getHermesWorkspacePreviewMode('blob.bin', 'application/octet-stream')).toBe(
			'unsupported'
		);
	});

	test('treats markdown, json, html, notebooks, and code as text previews', () => {
		expect(getHermesWorkspacePreviewMode('brief.md')).toBe('text');
		expect(getHermesWorkspacePreviewMode('data.json')).toBe('text');
		expect(getHermesWorkspacePreviewMode('index.html')).toBe('text');
		expect(getHermesWorkspacePreviewMode('analysis.ipynb')).toBe('text');
		expect(getHermesWorkspacePreviewMode('server.ts')).toBe('text');
	});
});
