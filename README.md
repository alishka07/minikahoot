# Quizo

Real-time quiz: React/Vinext + Tailwind/shadcn, Django REST Framework, Channels, Redis, PostgreSQL.

## Запуск

1. `docker compose up` — Postgres, Redis, миграции и ASGI-сервер на `:8000`.
2. `cd frontend && npm install && npm run dev` → `http://localhost:3000`.

Тесты бэкенда (без Postgres и Redis, на sqlite и in-memory слоях):

```bash
cd backend && python manage.py test game --settings=quiz.settings_test
```

## Как устроен синхронный старт

Время считает **сервер**, а не клиент. В `GameSession` лежат абсолютные метки:

| поле | смысл |
| --- | --- |
| `starts_at` | момент, когда вопрос открывается у всех |
| `ends_at` | дедлайн приёма ответов (`starts_at + duration_seconds`) |
| `reveal_ends_at` | до какого момента показываются результаты |

Когда ведущий жмёт «Начать», сессия переходит в статус `countdown` и `starts_at` ставится
на `now + COUNTDOWN_MS` (по умолчанию 3 с). Событие `countdown` уходит всем сразу — за эти
три секунды его успевают получить даже медленные устройства, клиент прогревает картинку и
рисует отсчёт 3-2-1. Ровно в `starts_at` серверный движок ([`game/engine.py`](backend/game/engine.py))
рассылает `game_started`, и вопрос открывается у всех **в один и тот же момент**.

Клиент не должен вести свой независимый отсчёт: он берёт из любого сообщения `server_time`,
считает поправку часов `offset = server_time - Date.now()` и рисует
`remaining = ends_at - (Date.now() + offset)`. Поэтому пинг и момент подключения ни на что
не влияют, а тот, кто зашёл посреди вопроса, получает в `state_sync` тот же `ends_at`, что и все.

Движок — отдельная asyncio-задача на комнату, а не обработчик соединения ведущего: игра
идёт по расписанию, даже если у ведущего отвалился сокет. Между процессами задачу защищает
блокировка в Redis, после рестарта цикл поднимается при первом же подключении.

## Живая статистика

Пока идёт вопрос, сервер раз в секунду шлёт `tick`: остаток времени, список участников
(кто онлайн, на каком вопросе, кто уже ответил) и счётчик ответов. Каждый ответ немедленно
порождает `stats_update` со временем реакции. Все действия дополнительно пишутся в таблицу
`GameEvent` (`joined` / `left` / `rejoined` / `answered` / `question_opened` / `question_closed` /
`game_started` / `game_finished`) — ленту можно и слушать по сокету, и дочитать через REST.

Распределение по вариантам и правильные ответы во время вопроса уходят **только ведущему**;
игроки получают их в `question_ended`, когда время вышло.

## WebSocket

`ws://host/ws/quiz/{room_code}/?role=host|player&token={host_token}&player={participant_token}`

### Сервер → клиент

| тип | когда | ключевые поля |
| --- | --- | --- |
| `state_sync` | при подключении, после входа, по запросу `sync` | `status`, `question`, `starts_at`, `ends_at`, `participants`, `stats`, `events`, `me` |
| `lobby_update` | кто-то зашёл / вышел / переподключился | `event`, `participant`, `participants`, `feed` |
| `countdown` | вопрос назначен | `question`, `starts_at`, `ends_at`, `index`, `total` |
| `game_started` | вопрос открыт | `question`, `starts_at`, `ends_at`, `index`, `total` |
| `tick` | раз в секунду во время вопроса | `remaining_ms`, `answered_count`, `participants`, `stats` |
| `stats_update` | кто-то ответил | `answered_count`, `answer_counts` (ведущему), `feed.response_ms` |
| `question_ended` | время вышло | `question.correct_options`, `stats.answer_counts`, `leaderboard` |
| `game_finished` | игра завершена | `participants`, `leaderboard` |
| `answer_result` | лично ответившему | `accepted`, `correct`, `points`, `score`, `response_ms` |
| `joined` | лично вошедшему | `participant_id`, `token` |
| `pong` | ответ на `ping` | `server_time`, `client_time` |
| `error` | ошибка | `message` |

Во всех сообщениях есть `server_time` — по нему клиент синхронизирует часы.

### Клиент → сервер

`join_lobby {name, token?}` · `sync` · `ping {t}` · `submit_answer {question_id, option_ids}`
и только для ведущего: `start_game` · `show_question {question_id}` · `next_question` ·
`end_question` · `finish_game` · `reset_game`.

Отказы при подключении: `4404` — комнаты нет, `4403` — неверный токен ведущего.

## REST

| метод | путь | назначение |
| --- | --- | --- |
| `POST` | `/api/rooms/` | создать комнату; **только в этом ответе** приходит `host_token` |
| `GET` | `/api/rooms/{code}/` | комната с вопросами (без правильных ответов) |
| `POST` | `/api/rooms/{code}/questions/` | вопрос или **список вопросов** одним запросом |
| `PATCH`/`DELETE` | `/api/rooms/{code}/questions/{id}/` | правка и удаление |
| `GET` | `/api/rooms/{code}/state/` | текущее состояние (то же, что `state_sync`) |
| `GET` | `/api/rooms/{code}/results/` | итоги: рейтинг, распределение и время ответа по каждому вопросу |
| `GET` | `/api/rooms/{code}/events/?after={id}` | лента действий, инкрементально |
| `POST` | `/api/rooms/{code}/close/` | закрыть комнату (нужен токен) |

Токен ведущего передаётся как `?token=` или заголовком `X-Host-Token`.

## Начисление очков

`points = max_points × (1 − elapsed/duration × (1 − MIN_RATIO))` за верный ответ, иначе 0.
При `MIN_RATIO=0.5` мгновенный ответ даёт 1000, ответ на последней секунде — 500.
`elapsed` считает сервер от `starts_at`, клиентскому времени не доверяем. Ответы принимаются
до `ends_at + GRACE_MS` (запас на сеть), но `elapsed` при этом не превышает длительность вопроса.
Повторный ответ невозможен: уникальность `(session, participant, question)` в БД.

## Схема данных

- `Room` — комната, код, `host_token`.
- `GameSession` — один прогон: статус (`lobby → countdown → question → reveal → finished`),
  текущий вопрос, серверные дедлайны. Новая игра в той же комнате = новая сессия, очки обнуляются,
  история прошлой игры остаётся.
- `Question` — `order`, варианты, правильные ответы, `duration_seconds`, `max_points`.
- `Participant` — привязан к комнате и к сессии; `connections` (сколько сокетов открыто),
  `is_online`, `stage`, `current_index` — то есть кто где сейчас находится.
- `Answer` — выбор, `is_correct`, `points`, `response_ms`, время; уникален в пределах сессии.
- `GameEvent` — лента всех действий с payload и временем.

## Настройки (`settings.QUIZ`)

| переменная | по умолчанию | что делает |
| --- | --- | --- |
| `QUIZ_QUESTION_SECONDS` | `10` | окно на ответ для новых вопросов |
| `QUIZ_COUNTDOWN_MS` | `3000` | задержка перед первым вопросом |
| `QUIZ_NEXT_LEAD_MS` | `1500` | задержка перед следующим вопросом |
| `QUIZ_REVEAL_MS` | `6000` | сколько показывать результаты в авто-режиме |
| `QUIZ_AUTO_ADVANCE` | `0` | `1` — сервер сам листает вопросы, без ведущего |
| `QUIZ_GRACE_MS` | `750` | запас на сетевую задержку ответа |
| `QUIZ_TICK_MS` | `1000` | частота лайв-трансляции |
| `QUIZ_MAX_POINTS` / `QUIZ_MIN_RATIO` | `1000` / `0.5` | формула очков |
| `QUIZ_REQUIRE_HOST_TOKEN` | `0` | `1` — без токена роль ведущего не выдаётся |

`QUIZ_REQUIRE_HOST_TOKEN=1` стоит включить в проде: иначе роль ведущего берётся из
query-параметра, и её может назвать любой. Значение `0` оставлено для совместимости
с текущим фронтендом, который токен пока не передаёт.

## Что стоит доделать на фронтенде

Бэкенд обратно совместим — старый клиент продолжает работать. Чтобы получить полную
картину, фронтенду остаётся: считать поправку часов по `server_time` и рисовать таймер от
`ends_at`; показывать отсчёт по `countdown`; восстанавливать экран из `state_sync` при
переподключении и входе посреди игры; рисовать ленту `feed`/`events` и `tick`; передавать
`host_token` в WS и хранить `participant token` для реконнекта.
