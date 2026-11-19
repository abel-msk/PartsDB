# SQLite: соединение и специфичные операции

Актуальность: 19 ноября 2026 года. Схема БД остаётся версии 6.

Работа с SQLite выделена в `ElData/ElDBConnect.py`. Модуль зависит только от
стандартной библиотеки и `ElLogger`, не импортирует Qt, схему приложения или
менеджер плагинов. `ElData/ElDBScheme.py` содержит определения таблиц, запросы
приложения, преобразование записей и последовательность миграций.
Корневой `connector.py` удалён.

## Методы SQLiteConnector

| Группа | Методы | Назначение |
|---|---|---|
| Соединение | `connect()`, `disconnect()`, `isConnect()` | Открыть SQLite-файл или `:memory:`, закрыть handle, проверить его назначение |
| Существующее соединение | `from_connection(connection)` | Обернуть `sqlite3.Connection`, не открывая и не копируя БД |
| Выполнение без commit | `execute(sql, values=())`, `executemany(sql, values)` | Передать параметризованный SQL драйверу SQLite |
| Чтение | `select(sql)`, `select_params(sql, values)`, `select_all(sql)` | Проверить завершённость SQL и вернуть курсор либо список строк |
| Одиночная запись | `exec(sql)`, `exec_insert(sql, values)` | Выполнить завершённый SQL, зафиксировать и вернуть последний ID |
| Транзакции | `begin(immediate=False)`, `commit()`, `rollback()`, `transaction(...)` | Начало, фиксация, откат и контекст транзакции |
| Состояние | `in_transaction` | Текущее состояние SQLite-транзакции |
| Внешние ключи | `get_foreign_keys()`, `set_foreign_keys(enabled)`, `foreign_key_violations()` | `PRAGMA foreign_keys` и `foreign_key_check` |
| Столбцы | `table_info(table)` | Прочитать `PRAGMA table_info` с безопасным quoting имени таблицы |
| Определения объектов | `table_definition(table)`, `schema_objects(table)` | Прочитать CREATE TABLE, индексы и триггеры из `sqlite_master` |
| AUTOINCREMENT | `sequence_value(table)`, `preserve_sequence(table, minimum)` | Прочитать и сохранить счётчик `sqlite_sequence`, не уменьшая его |

`DBError` описывает ошибку жизненного цикла или транзакции, `DBSyntax` —
незавершённый SQL или ошибку исполнения в методах одиночной записи. Классы
определены в `ElDBConnect.py`; `ElDBScheme` импортирует их для своих операций.

## Транзакции

```python
from ElData.ElDBConnect import SQLiteConnector

connection = SQLiteConnector(':memory:')
connection.connect()
try:
    # В обычном коде эти запросы формирует ElDBScheme, не интерфейс или сервис.
    with connection.transaction(require_idle=True, foreign_keys=True, immediate=True):
        connection.execute('CREATE TABLE example(id INTEGER PRIMARY KEY, value TEXT)')
        connection.execute('INSERT INTO example(value) VALUES (?)', ('text',))
finally:
    connection.disconnect()
```

Параметры `transaction()`:

- `require_idle=True` отвергает вложенный запуск, не фиксируя чужую незавершённую работу;
- `foreign_keys=None` сохраняет настройку; `True` или `False` меняет её до начала
  транзакции. Изменение во время активной транзакции запрещено;
- `immediate=True` начинает `BEGIN IMMEDIATE`, если транзакция ещё не началась.

Нормальный выход фиксирует изменения, исключение откатывает их. Выход из
контекста не закрывает соединение. Для многошаговой атомарной операции используют
`execute()` и `executemany()`. Методы `exec()` и `exec_insert()` выполняют commit
сами и предназначены для одиночных операций.

`DBScheme.transaction()` делегирует драйверу транзакцию с `require_idle=True`.
Миграции решают, какие таблицы перестроить, а драйвер обеспечивает временное
отключение и восстановление FK, проверку нарушений и сохранение счётчиков.
При восстановлении режима FK вызывающая миграция использует `finally`.

## Что остаётся в ElDBScheme

- DDL приложения, версия схемы и шаги миграции;
- запросы к `PARTS`, `TYPES`, `HEADERS`, `PROJECTS`, `PLUGINS` и другим таблицам;
- правила сохранения проекта, позиций и сопоставлений;
- выбор границ бизнес-транзакции и обработка её результата.

Это разделение не делает схему совместимой с произвольной СУБД: DDL и миграции
приложения по-прежнему рассчитаны на SQLite. Оно отделяет механизм соединения
и системные особенности SQLite от запросов предметной области.

## Импорты и тесты

```python
from ElData import ElDBScheme
from ElData.ElDBScheme import DBScheme, DBFactory
from ElData.ElDBConnect import SQLiteConnector, DBError, DBSyntax
```

Импорты корневого `ElDBScheme` и `connector` не используются. Менеджер плагинов
расположен в `ElPluginMgr`; runtime установленных плагинов содержит только
`ElPluginMgr.protocol`, worker и публичный SDK, без SQLite-драйвера и Qt.

```sh
python -m unittest tests.test_db_connect tests.test_database_access_boundary -v
./build.sh -t
```

Тесты драйвера работают с `:memory:`. Проверяются атомарность, безопасная привязка
параметров, вложенные транзакции, внешние ключи, метаданные, кавычки в именах,
AUTOINCREMENT и импорт без Qt. Архитектурная проверка допускает SQL приложения
только в `ElData/ElDBScheme.py`, а SQLite API и системные запросы — только
в `ElData/ElDBConnect.py`. Прямой SQL в тестах разрешён.

После полного прогона очистка или ротация тестовых БД выполняется `build.sh`
по правилам [AGENTS.md](../AGENTS.md).
