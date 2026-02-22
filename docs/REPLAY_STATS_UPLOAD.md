# Страница статистики реплеев (v1)

Дата: 2026-02-22

## Что реализовано

1. Добавлена приватная вкладка профиля `Статистика`: `profile/stats/`.
2. Добавлен отдельный endpoint загрузки реплеев для статистики: `profile/stats/upload/`.
3. Добавлен endpoint экспорта статистики: `profile/stats/export/`.
4. Новый поток загрузки читает `.mtreplay` только в памяти и не сохраняет:
- файл реплея на диск;
- полный `payload` в БД.
5. При загрузке одного реплея сохраняются строки по всем союзникам владельца реплея.
6. В БД сохраняются только основные параметры боя в модели `ReplayStatBattle` и связанные строки игроков в `ReplayStatPlayer`.
7. Реализована дедупликация на уровне:
- боя: `пользователь + battle_signature`;
- игрока в бою: `battle + player_account_id`.

## Модели

`ReplayStatBattle`:
- `user`
- `battle_date`
- `map_name`, `map_display_name`
- `outcome` (`win` / `loss` / `draw`)
- `arena_unique_id` (опционально)
- `battle_signature`
- `created_at`

`ReplayStatPlayer`:
- `battle` (FK -> `ReplayStatBattle`)
- `player_account_id`, `player_name`
- `tank` (опциональный FK), `tank_tag`, `tank_name` (fallback)
- `damage`, `xp`, `kills`, `assist`, `block`
- `created_at`

## Правила дедупликации

Сигнатура боя вычисляется детерминированно:

1. Если есть `arena_unique_id`:
- raw-signature: `arena:{arena_unique_id}`

2. Если `arena_unique_id` отсутствует:
- raw-signature: `fallback:{player_account_id}:{battle_date_utc_iso}:{tank_tag}`

3. `battle_signature = sha256(raw-signature).hexdigest()`

Ограничение уникальности на уровне БД:
- `ReplayStatBattle`: `unique_stat_battle_user_signature`.
- `ReplayStatPlayer`: `unique_stat_player_per_battle`.

## Контракт API загрузки

`POST /profile/stats/upload/` (AJAX, `X-Requested-With: XMLHttpRequest`)

Вход:
- `files[]`: один или несколько `.mtreplay`.

Техническое ограничение v1:
- максимум `20` файлов за один запрос.

Успешный ответ:

```json
{
  "success": true,
  "summary": {
    "processed": 3,
    "created": 2,
    "duplicates": 1,
    "errors": 0
  },
  "results": [
    {"file": "a.mtreplay", "ok": true, "status": "created", "rows_created": 2, "rows_duplicates": 0, "rows_total": 2},
    {"file": "b.mtreplay", "ok": true, "status": "duplicate", "rows_created": 0, "rows_duplicates": 2, "rows_total": 2},
    {"file": "c.mtreplay", "ok": false, "status": "error", "error": "message"}
  ],
  "redirect_url": "/profile/stats/"
}
```

Возможные `status` по файлу:
- `created`
- `duplicate`
- `error`

## Экспорт статистики

`GET /profile/stats/export/` возвращает `xlsx`-файл.

Поддерживаются параметры периода:
- `date_from` (YYYY-MM-DD)
- `date_to` (YYYY-MM-DD)

Формат таблицы:
- столбец `A`: ник игрока;
- столбцы `B..N`: реплеи/бои (`Бой 1`, `Бой 2`, ...);
- в ячейках: урон игрока в конкретном бою (пусто, если игрока в бою не было);
- последний столбец: `С/У` (средний урон игрока).

Матрица строится по записям текущего авторизованного пользователя.
