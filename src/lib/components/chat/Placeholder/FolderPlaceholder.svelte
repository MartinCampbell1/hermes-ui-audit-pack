<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';

	const i18n: Writable<any> = getContext('i18n');

	import ChatList from './ChatList.svelte';
	import FolderKnowledge from './FolderKnowledge.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { getChatListByFolderId } from '$lib/apis/chats';
	import { refreshHermesSessionStores } from '$lib/utils/hermesSessions';

	export let folder: any = null;

	let selectedTab = 'chats';

	let page = 1;

	let chats: any[] | null = null;
	let chatListLoading = false;
	let allChatsLoaded = false;

	const loadChats = async () => {
		chatListLoading = true;

		page += 1;

		let newChatList: any[] = [];

		newChatList = await getChatListByFolderId(localStorage.token, folder.id, page).catch(
			(error) => {
				console.error(error);
				return [];
			}
		);

		// once the bottom of the list has been reached (no results) there is no need to continue querying
		allChatsLoaded = newChatList.length === 0;
		chats = [...(chats || []), ...(newChatList || [])];

		chatListLoading = false;
	};

	const setChatList = async () => {
		chats = null;
		page = 1;
		allChatsLoaded = false;
		chatListLoading = false;

		if (folder && folder.id) {
			await refreshHermesSessionStores(localStorage.token).catch((error) => {
				console.debug('Failed to refresh Hermes sessions for folder chats:', error);
			});

			const res = await getChatListByFolderId(localStorage.token, folder.id, page);

			if (res) {
				chats = res;
			} else {
				chats = [];
			}
		} else {
			chats = [];
		}
	};

	$: if (folder) {
		setChatList();
	}
</script>

<div>
	<!-- <div class="mb-1">
		<div
			class="flex gap-1 scrollbar-none overflow-x-auto w-fit text-center text-sm font-medium rounded-full bg-transparent py-1 touch-auto pointer-events-auto"
		>
			<button
				class="min-w-fit p-1.5 {selectedTab === 'knowledge'
					? ''
					: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition"
				type="button"
				on:click={() => {
					selectedTab = 'knowledge';
				}}>{$i18n.t('Knowledge')}</button
			>

			<button
				class="min-w-fit p-1.5 {selectedTab === 'chats'
					? ''
					: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition"
				type="button"
				on:click={() => {
					selectedTab = 'chats';
				}}
			>
				{$i18n.t('Chats')}
			</button>
		</div>
	</div> -->

	<div class="">
		{#if selectedTab === 'knowledge'}
			<FolderKnowledge />
		{:else if selectedTab === 'chats'}
			{#if folder?.id}
				<div class="px-1 pb-2 text-[11px] leading-4 text-gray-400 dark:text-gray-500">
					{$i18n.t('Chats in this folder stay linked to Hermes sessions.')}
				</div>
			{/if}

			{#if chats !== null}
				<ChatList {chats} {chatListLoading} {allChatsLoaded} loadHandler={loadChats} />
			{:else}
				<div class="py-10">
					<Spinner />
				</div>
			{/if}
		{/if}
	</div>
</div>
