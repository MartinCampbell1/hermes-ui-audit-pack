## Hermes Live Preserve Bundle

Этот bundle нужен для быстрого восстановления только утвержденных live-кастомизаций Hermes после `hermes update`.
Теперь он работает через patch stack, а не через копирование целых Python-файлов поверх upstream.

Что сохраняется:
- browser OAuth login для `openai-codex`
- пул / ротация аккаунтов
- ранний failover / preflight account selection для длинных задач
- связанные CLI/runtime auth surfaces
- патч `cli.py`, который не даёт background/system событиям уходить в обычный chat input
- thread-aware session model для UI:
  - `thread_id`
  - `session_kind`
  - `is_user_visible`
  - canonical thread listing / export вместо сотен raw child sessions
- Codex runtime fixes для auxiliary path
- текущий upstream `run_agent.py` с нашим ранним 429 rotation patch
- `~/.hermes/config.yaml`
- `~/.hermes/auth.json` с уже авторизованными аккаунтами

Как именно сохраняется:
- `auth.json` и `config.yaml` остаются file-snapshot
- кодовые изменения теперь лежат как patch stack в `patches/*.patch`
- restore применяет их через `git apply --3way`
- это снижает риск затереть новые upstream-команды целым старым файлом

Что НЕ сохраняется:
- compaction / handoff / reactive compaction слой
- старый compat-resume runtime

Основной сценарий:
1. Обновляешь Hermes обычным способом.
2. Запускаешь `Restore Hermes After Update.command` на рабочем столе.
3. Перезапускаешь Hermes.

Canary-сценарий для будущих обновлений:
1. Запускаешь `prepare_canary.command` из этой папки.
2. Скрипт поднимает отдельный canary Hermes в `~/Desktop/hermes-canary-home` и собирает ему собственный `.venv`.
3. Прогоняешь smoke-проверки на canary.
4. Только потом обновляешь live Hermes и запускаешь restore.

Что делает restore:
- сохраняет rollback-копию текущих live-файлов перед перезаписью
- возвращает `config.yaml`
- возвращает `auth.json`, чтобы не потерять текущие OAuth-сессии
- применяет approved patch stack поверх чистого upstream через `git apply --3way`
- при провале patch apply откатывает live-файлы из rollback-копии

Этот restore намеренно оставляет upstream continuation / compaction как есть.

Дополнительно:
- после restore можно прогнать `/Users/martin/HERMES_UPDATE_INFO/export_real_sessions.command`
- это создаст thread-level экспорт настоящих пользовательских сессий для внешнего UI

Если позже ты ещё поменяешь live-кастомизации вручную и захочешь обновить snapshot:
- запусти `refresh_hermes_snapshot.command`

Важно:
- в bundle лежит `auth.json`, то есть это приватная папка
- не публикуй её и не кидай в git / облако
