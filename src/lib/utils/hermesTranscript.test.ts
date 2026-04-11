import { describe, expect, test } from 'vitest';

import {
	getCurrentBranchLatestAssistantMessageId,
	getHermesComposerActivityMessageId,
	getHermesImportedToolContent,
	getHermesImportedToolName,
	getHermesImportedToolSummary,
	getHermesStatusEntries,
	getHermesToolExecutionState,
	getHermesVisibleStatusEntries,
	isHermesImportedToolMessage,
	normalizeHermesStreamEventName,
	upsertHermesToolExecution
} from './hermesTranscript';

describe('getHermesStatusEntries', () => {
	test('prefers status history and falls back to single status', () => {
		expect(
			getHermesStatusEntries({
				statusHistory: [{ description: 'Running' }],
				status: { description: 'Done' }
			})
		).toEqual([{ description: 'Running' }]);

		expect(
			getHermesStatusEntries({
				status: { description: 'Done' }
			})
		).toEqual([{ description: 'Done' }]);

		expect(getHermesStatusEntries(null)).toEqual([]);
	});
});

describe('getHermesVisibleStatusEntries', () => {
	test('filters pseudo tool statuses when real tool executions are present', () => {
		expect(
			getHermesVisibleStatusEntries({
				statusHistory: [
					{ action: 'hermes_session', description: 'Sending' },
					{ action: 'hermes_tool', description: 'shell: ls' }
				],
				code_executions: [{ id: 'tool-1', name: 'shell' }]
			})
		).toEqual([{ action: 'hermes_session', description: 'Sending' }]);
	});

	test('keeps tool statuses when no real tool executions exist yet', () => {
		expect(
			getHermesVisibleStatusEntries({
				statusHistory: [{ action: 'hermes_tool', description: 'shell: ls' }]
			})
		).toEqual([{ action: 'hermes_tool', description: 'shell: ls' }]);
	});
});

describe('imported tool helpers', () => {
	test('prefers explicit tool name and strips legacy tool prefix from content', () => {
		const message = {
			role: 'tool',
			toolName: 'shell',
			content: '[Tool: shell]\n{"ok": true}'
		};

		expect(getHermesImportedToolName(message)).toBe('shell');
		expect(getHermesImportedToolContent(message)).toBe('{"ok": true}');
		expect(getHermesImportedToolSummary(message)).toBe('{"ok": true}');
	});

	test('summarizes command-style JSON payload output without losing raw detail content', () => {
		const message = {
			role: 'tool',
			toolName: 'shell',
			content:
				'[Tool: shell]\n{"output":"ACCOUNT PLAN 5H USAGE\\nweekly details","exit_code":0,"error":null}'
		};

		expect(getHermesImportedToolSummary(message)).toBe('ACCOUNT PLAN 5H USAGE');
		expect(getHermesImportedToolContent(message)).toContain('"output"');
	});

	test('prefers failure text for command-style JSON payloads', () => {
		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				content: '[Tool: shell]\n{"output":"partial output","exit_code":1,"error":"permission denied"}'
			})
		).toBe('permission denied');

		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				content: '[Tool: shell]\n{"output":"","exit_code":2,"error":null}'
			})
		).toBe('exit code: 2');

		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				content: '[Tool: shell]\n{"success":true,"message":"ok"}'
			})
		).toBe('Success');
	});

	test('summarizes common Hermes search and file payloads structurally', () => {
		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				toolName: 'search',
				content: '[Tool: search]\n{"total_count":19,"files":[{"path":"a.ts"}]}'
			})
		).toBe('Found 19 files');

		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				toolName: 'grep',
				content: '[Tool: grep]\n{"total_count":346,"matches":[{"path":"a.ts","line":1}]}'
			})
		).toBe('Found 346 matches');

		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				content: '[Tool: memory]\n{"success":true,"query":"sessions","results":[{},{}]}'
			})
		).toBe('query: sessions (2 results)');
	});

	test('uses content text from JSON payloads when available', () => {
		expect(
			getHermesImportedToolSummary({
				role: 'tool',
				content: '[Tool: read]\n{"content":"     1|from __future__ import annotations\\n     2|"}'
			})
		).toBe('1|from __future__ import annotations');
	});

	test('falls back to tool prefix or generic label when name is missing', () => {
		expect(
			getHermesImportedToolName({
				role: 'tool',
				content: '[Tool: planner]\ncompleted'
			})
		).toBe('planner');

		expect(getHermesImportedToolName({ role: 'tool', content: 'raw output' })).toBe('tool');
		expect(getHermesImportedToolSummary({ role: 'tool', content: '' })).toBe('Completed');
	});

	test('detects imported tool messages from role or sourceRole', () => {
		expect(isHermesImportedToolMessage({ role: 'tool' })).toBe(true);
		expect(isHermesImportedToolMessage({ role: 'assistant', sourceRole: 'tool' })).toBe(true);
		expect(isHermesImportedToolMessage({ role: 'assistant' })).toBe(false);
	});
});

describe('normalizeHermesStreamEventName', () => {
	test('maps known stream aliases onto stable frontend events', () => {
		expect(normalizeHermesStreamEventName('approval.pending')).toBe('approval');
		expect(normalizeHermesStreamEventName('approval.resolved')).toBe('approval.resolved');
		expect(normalizeHermesStreamEventName('tool.finished')).toBe('tool');
		expect(normalizeHermesStreamEventName('run.completed')).toBe('run.completed');
		expect(normalizeHermesStreamEventName('run.started')).toBe('run.started');
		expect(normalizeHermesStreamEventName('warning')).toBe('warning');
	});
});

describe('live Hermes tool executions', () => {
	test('derives tool execution state from event payloads', () => {
		expect(getHermesToolExecutionState({ event: 'tool.started' })).toBe('running');
		expect(getHermesToolExecutionState({ event: 'tool.completed', result: {} })).toBe('done');
		expect(getHermesToolExecutionState({ event: 'tool.error', error: 'permission denied' })).toBe(
			'failed'
		);
	});

	test('appends running execution rows and updates them on completion', () => {
		const runningExecutions = upsertHermesToolExecution([], {
			event: 'tool.started',
			name: 'shell',
			preview: 'ls -la'
		});

		expect(runningExecutions).toHaveLength(1);
		expect(runningExecutions[0]).toMatchObject({
			name: 'shell',
			preview: 'ls -la',
			result: null
		});

		const completedExecutions = upsertHermesToolExecution(runningExecutions, {
			event: 'tool.finished',
			name: 'shell',
			preview: '2 files',
			files: [{ path: '/tmp/a.txt' }]
		});

		expect(completedExecutions).toHaveLength(1);
		expect(completedExecutions[0].result).toMatchObject({
			output: '2 files',
			files: [{ path: '/tmp/a.txt' }]
		});
	});

	test('stamps timing metadata for live executions', () => {
		const beforeStart = Date.now();
		const runningExecutions = upsertHermesToolExecution([], {
			event: 'tool.started',
			name: 'shell',
			preview: 'ls -la'
		});

		expect(runningExecutions[0].started_at).toBeGreaterThanOrEqual(beforeStart);
		expect(runningExecutions[0].updated_at).toBeGreaterThanOrEqual(runningExecutions[0].started_at);

		const completedExecutions = upsertHermesToolExecution(runningExecutions, {
			event: 'tool.finished',
			name: 'shell',
			preview: 'done'
		});

		expect(completedExecutions[0].completed_at).toBeGreaterThanOrEqual(
			completedExecutions[0].started_at
		);
		expect(completedExecutions[0].updated_at).toBeGreaterThanOrEqual(
			completedExecutions[0].started_at
		);
	});

	test('adds failed execution results when tool errors arrive', () => {
		expect(
			upsertHermesToolExecution([], {
				event: 'tool.error',
				name: 'shell',
				error: 'permission denied'
			})[0]
		).toMatchObject({
			name: 'shell',
			result: {
				error: 'permission denied'
			}
		});
	});
});

describe('getCurrentBranchLatestAssistantMessageId', () => {
	test('returns the latest assistant on the active branch', () => {
		expect(
			getCurrentBranchLatestAssistantMessageId({
				currentId: 'user2',
				messages: {
					root: { id: 'root', parentId: null, role: 'system' },
					user1: { id: 'user1', parentId: 'root', role: 'user' },
					assistant1: { id: 'assistant1', parentId: 'user1', role: 'assistant' },
					user2: { id: 'user2', parentId: 'assistant1', role: 'user' }
				}
			})
		).toBe('assistant1');
	});
});

describe('getHermesComposerActivityMessageId', () => {
	test('returns the latest assistant when it has visible status activity', () => {
		expect(
			getHermesComposerActivityMessageId({
				currentId: 'assistant1',
				messages: {
					root: { id: 'root', parentId: null, role: 'system' },
					assistant1: {
						id: 'assistant1',
						parentId: 'root',
						role: 'assistant',
						statusHistory: [{ description: 'Working', hidden: false }]
					}
				}
			})
		).toBe('assistant1');
	});

	test('returns the latest assistant when it has tool activity even without visible status', () => {
		expect(
			getHermesComposerActivityMessageId({
				currentId: 'user2',
				messages: {
					root: { id: 'root', parentId: null, role: 'system' },
					assistant1: {
						id: 'assistant1',
						parentId: 'root',
						role: 'assistant',
						code_executions: [{ id: 'tool-1', name: 'run-tool' }]
					},
					user2: { id: 'user2', parentId: 'assistant1', role: 'user' }
				}
			})
		).toBe('assistant1');
	});

	test('does not surface stale activity from older assistant turns', () => {
		expect(
			getHermesComposerActivityMessageId({
				currentId: 'assistant2',
				messages: {
					root: { id: 'root', parentId: null, role: 'system' },
					user1: { id: 'user1', parentId: 'root', role: 'user' },
					assistant1: {
						id: 'assistant1',
						parentId: 'user1',
						role: 'assistant',
						statusHistory: [{ description: 'Generated files' }]
					},
					user2: { id: 'user2', parentId: 'assistant1', role: 'user' },
					assistant2: {
						id: 'assistant2',
						parentId: 'user2',
						role: 'assistant',
						content: 'Final answer'
					}
				}
			})
		).toBeNull();
	});

	test('respects hidden final statuses and disabled status updates', () => {
		expect(
			getHermesComposerActivityMessageId({
				currentId: 'assistant1',
				messages: {
					root: { id: 'root', parentId: null, role: 'system' },
					assistant1: {
						id: 'assistant1',
						parentId: 'root',
						role: 'assistant',
						statusHistory: [{ description: 'Hidden', hidden: true }]
					}
				}
			})
		).toBeNull();

		expect(
			getHermesComposerActivityMessageId(
				{
					currentId: 'assistant1',
					messages: {
						root: { id: 'root', parentId: null, role: 'system' },
						assistant1: {
							id: 'assistant1',
							parentId: 'root',
							role: 'assistant',
							statusHistory: [{ description: 'Visible', hidden: false }]
						}
					}
				},
				{ statusUpdatesEnabled: false }
			)
		).toBeNull();
	});
});
