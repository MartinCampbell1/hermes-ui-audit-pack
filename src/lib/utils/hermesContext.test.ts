import { describe, expect, test } from 'vitest';

import { buildHermesContextSummary, formatWorkspaceNameFromPath, getActiveHermesProfile } from './hermesContext';

describe('formatWorkspaceNameFromPath', () => {
	test('returns the trailing directory name for normalized paths', () => {
		expect(formatWorkspaceNameFromPath('/Users/martin/projects/hermes/')).toBe('hermes');
		expect(formatWorkspaceNameFromPath('/tmp/workspace')).toBe('workspace');
	});

	test('returns an empty string for missing paths', () => {
		expect(formatWorkspaceNameFromPath('')).toBe('');
		expect(formatWorkspaceNameFromPath(null)).toBe('');
	});
});

describe('getActiveHermesProfile', () => {
	test('prefers the active profile and falls back to the first item', () => {
		expect(
			getActiveHermesProfile({
				target_id: 'local',
				active_home: '/tmp/hermes',
				active_profile: 'ops',
				items: [
					{ name: 'default', path: '/profiles/default', is_default: true, is_active: false },
					{ name: 'ops', path: '/profiles/ops', is_default: false, is_active: true }
				]
			} as any)?.name
		).toBe('ops');

		expect(
			getActiveHermesProfile({
				target_id: 'local',
				active_home: '/tmp/hermes',
				active_profile: 'default',
				items: [{ name: 'default', path: '/profiles/default', is_default: true, is_active: false }]
			} as any)?.name
		).toBe('default');
	});
});

describe('buildHermesContextSummary', () => {
	test('prefers session context over profile defaults and browser fallback', () => {
		expect(
			buildHermesContextSummary({
				chatHermesSession: {
					session_id: 'session-1',
					profile: 'ops',
					model: 'openai/gpt-5.4',
					target_id: 'local'
				},
				runtime: {
					target_id: 'runtime-target',
					active_home: '/tmp/hermes',
					active_profile: 'default',
					python_path: '/usr/bin/python',
					state_db_path: '/tmp/state.db',
					session_dir: '/tmp/sessions'
				},
				workspaces: {
					target_id: 'local',
					active_home: '/tmp/hermes',
					active_profile: 'ops',
					last_workspace: '/tmp/hermes/workspaces/client',
					items: [
						{
							name: 'client',
							path: '/tmp/hermes/workspaces/client',
							is_active: true
						}
					]
				},
				profiles: {
					target_id: 'local',
					active_home: '/tmp/hermes',
					active_profile: 'ops',
					items: [
						{
							name: 'ops',
							path: '/profiles/ops',
							is_default: false,
							is_active: true,
							model: 'anthropic/claude',
							has_env: true,
							has_soul: true,
							has_memory: true,
							has_user_profile: true,
							memory_enabled: true,
							user_profile_enabled: false,
							gateway_running: true,
							skill_count: 18
						}
					]
				} as any,
				workspaceStatus: {
					source: 'terminal',
					currentPath: '/tmp/hermes/workspaces/client',
					itemCount: 12,
					visibleItemCount: 7,
					linkedItemCount: 3,
					selectedFileName: 'plan.md'
				},
				currentMessageId: 'assistant-1',
				selectedModelLabel: 'gpt-4o-mini',
				generatedFileCount: 2,
				chatAttachedFileCount: 4,
				taskCount: 6
			})
		).toMatchObject({
			workspaceLabel: 'client',
			workspacePath: '/tmp/hermes/workspaces/client',
			workspaceSource: 'terminal',
			profileLabel: 'ops',
			sessionStateLabel: 'Active',
			sessionId: 'session-1',
			targetId: 'local',
			activeModelLabel: 'openai/gpt-5.4',
			modelSource: 'session',
			browserFallbackModelLabel: 'gpt-4o-mini',
			workspaceVisibleCount: 7,
			linkedFileCount: 3,
			generatedFileCount: 2,
			chatAttachedFileCount: 4,
			taskCount: 6,
			profileSkillCount: 18,
			profileMemoryEnabled: true,
			userProfileEnabled: false
		});
	});

	test('falls back to the active profile model and current chat state when no session exists', () => {
		expect(
			buildHermesContextSummary({
				chatHermesSession: null,
				chatMeta: null,
				runtime: {
					target_id: 'local',
					active_home: '/tmp/hermes',
					active_profile: 'default',
					python_path: '/usr/bin/python',
					state_db_path: '/tmp/state.db',
					session_dir: '/tmp/sessions'
				},
				workspaces: {
					target_id: 'local',
					active_home: '/tmp/hermes',
					active_profile: 'default',
					last_workspace: '/tmp/hermes/workspaces/sessions',
					items: []
				},
				profiles: {
					target_id: 'local',
					active_home: '/tmp/hermes',
					active_profile: 'default',
					items: [
						{
							name: 'default',
							path: '/profiles/default',
							is_default: true,
							is_active: true,
							model: 'gpt-5.4-mini',
							has_env: true,
							has_soul: false,
							has_memory: false,
							has_user_profile: false,
							memory_enabled: false,
							user_profile_enabled: false,
							gateway_running: true,
							skill_count: 4
						}
					]
				} as any,
				currentMessageId: 'user-1',
				selectedModelLabel: 'browser-only-model'
			})
		).toMatchObject({
			workspaceLabel: 'sessions',
			profileLabel: 'default',
			sessionStateLabel: 'Current chat',
			activeModelLabel: 'gpt-5.4-mini',
			modelSource: 'profile'
		});
	});

	test('marks the model as browser fallback when no Hermes model is available', () => {
		expect(
			buildHermesContextSummary({
				selectedModelLabel: 'browser-only-model'
			})
		).toMatchObject({
			activeModelLabel: 'browser-only-model',
			modelSource: 'fallback',
			browserFallbackModelLabel: 'browser-only-model'
		});
	});

	test('uses workspace status and current chat state when Hermes runtime context is absent', () => {
		expect(
			buildHermesContextSummary({
				workspaceStatus: {
					source: 'terminal',
					currentPath: '/tmp/hermes/workspaces/staging',
					itemCount: 0
				},
				currentMessageId: 'assistant-42',
				selectedModelLabel: 'browser-only-model'
			})
		).toMatchObject({
			workspaceLabel: 'staging',
			workspacePath: '/tmp/hermes/workspaces/staging',
			workspaceSource: 'terminal',
			profileLabel: '',
			sessionStateLabel: 'Current chat',
			sessionId: null,
			targetId: null,
			activeModelLabel: 'browser-only-model',
			modelSource: 'fallback',
			browserFallbackModelLabel: 'browser-only-model'
		});
	});
});
