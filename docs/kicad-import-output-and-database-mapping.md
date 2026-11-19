# KiCad: пример результата импорта и раскладка по таблицам БД

Дата: 19 ноября 2026 года. Версия схемы БД приложения: 6.

Документ фиксирует фактический результат вызова текущего импортёра на тестовых
данных репозитория и правила его сохранения. Импортёр, сборка wheel и слой
транзакционного сохранения результата импорта реализованы; см. [порядок работы](plugin-runtime.md). При подготовке
документа БД не изменялась.

## 1. Источники и вызов

Входной проект:
`tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro`.

Связанные схемы в той же директории:

- `SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_sch`;
- `ExtConnectors.kicad_sch`;
- `PowerSupply.kicad_sch`.

Вызов из корня репозитория с `PYTHONPATH=ElPartsPluginSrc/kicad:.`:

```python
from pathlib import Path
from partsdb_kicad import KiCadImporter

source = Path(
    'tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/'
    'SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro'
).resolve().as_uri()

importer = KiCadImporter()
project = importer.import_project(source)  # ImportedProject
components = project.components          # list[ImportedComponent]
# Если нужен только список: importer.get_components(source)
```

## 2. Пример результата

Возвращается Python-объект `ImportedProject` с 49 объектами `ImportedComponent`.
Ниже — JSON-представление через `dataclasses.asdict()`: метаданные проекта
приведены полностью, а в массиве `components` оставлена только первая позиция C1.
Остальные 48 позиций перечислены в таблице раздела 3. Абсолютные пути соответствуют
расположению репозитория при подготовке документа.

```json
{
  "name": "SMHome_UniversalRound_ESP32_C3_Mini_v4",
  "description": "Smart home relay board.",
  "external_id": "1a9f0d73-6986-450b-8da5-dca8d718cd0d",
  "properties": {
    "source_files": [
      "/Users/abel/Developing/PartsDB/tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_sch",
      "/Users/abel/Developing/PartsDB/tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/ExtConnectors.kicad_sch",
      "/Users/abel/Developing/PartsDB/tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/PowerSupply.kicad_sch"
    ]
  },
  "components": [
    {
      "external_id": "/1a9f0d73-6986-450b-8da5-dca8d718cd0d/26ba38b8-de6a-4290-840f-c0381062839e/01b136d3-50db-47bc-9e3a-bd2417f28c2f",
      "reference": "C1",
      "kind": "capacitor",
      "value_raw": "100nF",
      "nominal": {
        "value": "0.0000001",
        "unit": "F"
      },
      "model": null,
      "symbol_id": "Device:C_Small",
      "footprint": "Capacitor_SMD:C_0805_2012Metric",
      "description": "Unpolarized capacitor, small symbol",
      "in_bom": true,
      "on_board": true,
      "dnp": false,
      "properties": {
        "Reference": "C1",
        "Value": "100nF",
        "Footprint": "Capacitor_SMD:C_0805_2012Metric",
        "Datasheet": "~",
        "Description": "",
        "comments": "6v",
        "kicad_symbol_uuids": [
          "01b136d3-50db-47bc-9e3a-bd2417f28c2f"
        ]
      }
    }
  ],
  "warnings": []
}
```

Предупреждений нет: `warnings = []`. У всех 49 позиций `in_bom = true`,
`on_board = true`, `dnp = false`.

Распределение категорий:

| kind | Количество |
| --- | --- |
| capacitor | 9 |
| diode | 9 |
| fuse | 1 |
| connector | 7 |
| test_point | 4 |
| other | 4 |
| inductor | 1 |
| resistor | 11 |
| module | 1 |
| ic | 2 |

## 3. Полный перечень возвращённых позиций

Категории ниже — фактический результат текущего алгоритма классификации плагина.
TP2–TP5 возвращаются как `test_point`, JP1–JP3 и VR1 — как `other`.
`NULL` в столбце номинала означает, что нормализованный номинал не возвращён;
исходное значение при этом сохранено в `value_raw`.

| reference | kind | value_raw | nominal | footprint |
| --- | --- | --- | --- | --- |
| C1 | capacitor | 100nF | 0.0000001 F | Capacitor_SMD:C_0805_2012Metric |
| C2 | capacitor | 4,7uF | 0.0000047 F | Capacitor_THT:CP_Radial_D8.0mm_P3.80mm |
| C3 | capacitor | 1uF | 0.000001 F | Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder |
| C4 | capacitor | 10uF | 0.00001 F | Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder |
| C5 | capacitor | 680uF | 0.00068 F | Capacitor_THT:CP_Radial_D6.3mm_P2.50mm |
| C6 | capacitor | 10uF | 0.00001 F | Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder |
| C9 | capacitor | 4.7uF | 0.0000047 F | Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder |
| C11 | capacitor | 100nF | 0.0000001 F | Capacitor_SMD:C_0805_2012Metric |
| C12 | capacitor | 100nF | 0.0000001 F | Capacitor_SMD:C_0805_2012Metric |
| D1 | diode | PESD3V3L1BA | NULL | Diode_SMD:D_SOD-323_HandSoldering |
| D5 | diode | PESD3V3L1BA | NULL | Diode_SMD:D_SOD-323_HandSoldering |
| D6 | diode | 1N4007W (A7) | NULL | Diode_SMD:D_SOD-123F |
| D7 | diode | ES1J | NULL | Diode_SMD:D_SMA |
| D8 | diode | E1J/FR107 | NULL | Diode_SMD:D_SOD-123F |
| D9 | diode | PESD3V3L1BA | NULL | Diode_SMD:D_SOD-323_HandSoldering |
| D11 | diode | PESD3V3L1BA | NULL | Diode_SMD:D_SOD-323_HandSoldering |
| D12 | diode | PESD3V3L1BA | NULL | Diode_SMD:D_SOD-323_HandSoldering |
| DB1 | diode | MB8S | NULL | Diode_local:MBS |
| F1 | fuse | 250v/0.12A | NULL | Fuse_Local:RF145_D6.5mm_W4mm |
| J1 | connector | pin header | NULL | Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical |
| J2 | connector | K128_P4 | NULL | Connector_Phoenix_MPT:Phoenix Contact_MPT-0,5_4_2,54_P4 |
| J3 | connector | Disp | NULL | Connector_JST:JST_PH_S9B-PH-SM4-TB_1x09-1MP_P2.00mm_Horizontal |
| J4 | connector | 220V | NULL | TerminalBlock_Degson:DG301-5.0-03P |
| J5 | connector | pin header | NULL | Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical |
| J6 | connector | JST SH | NULL | Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal |
| J7 | connector | USB_C_Receptacle_PowerOnly_6P | NULL | Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal |
| JP1 | other | to ADC | NULL | Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm |
| JP2 | other | to ADC | NULL | Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm |
| JP3 | other | to ADC | NULL | Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm |
| L1 | inductor | 320uH | 0.00032 H | Inductor_THT:L_Radial_D10.0mm_P5.00mm_Fastron_07P |
| R1 | resistor | 1K | 1000 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R2 | resistor | 600R | 600 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R5 | resistor | 10 | 10 ohm | Resistor_THT:R_Axial_DIN0414_L11.9mm_D4.5mm_P5.08mm_Vertical |
| R6 | resistor | 4.7K | 4700 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R7 | resistor | 4.7K | 4700 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R11 | resistor | 600R | 600 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R12 | resistor | 600R | 600 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R14 | resistor | 0,3 | 0.3 ohm | Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder |
| R19 | resistor | 100R | 100 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R20 | resistor | 1K | 1000 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| R21 | resistor | 1K | 1000 ohm | Resistor_SMD:R_0603_1608Metric_Pad0.98x0.95mm_HandSolder |
| TP2 | test_point | TestPoint | NULL | TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm |
| TP3 | test_point | TestPoint | NULL | TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm |
| TP4 | test_point | TestPoint | NULL | TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm |
| TP5 | test_point | TestPoint | NULL | TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm |
| U1 | module | ESP32 C3 Pro Mini | NULL | WIFI_Module:ESP32-C3_Pro_mini_no_keepout |
| U2 | ic | BP2525F | NULL | Package_SO_Local:SOT33-5 |
| U3 | ic | AMS1117-3.3 | NULL | Package_SO_Local:SOT-223-3_TabPin1 |
| VR1 | other | 07D471K | NULL | Varistor:RV_Disc_D9mm_W3.3mm_P5mm |

## 4. Запись проекта: PROJECTS

До импорта установленный плагин уже имеет строку в `PLUGINS`. Для KiCad:
`id = org.partsdb.kicad`, `plugin_type = project_import`, `version = 0.1.0`,
`api_version = 1`, `system_id = kicad`, `system_name = KiCad`.
Полный манифест хранится в `manifest_json`. Метод `get_plugin_type()` возвращает
`PLUGIN_TYPE_IMPORT`; несовпадение типа исключает установку или выполнение.


При первом импорте создаётся одна запись проекта. При повторном импорте
обновляется существующий проект, выбранный в PartsDB.

| Поле БД | Источник | Пример / правило |
| --- | --- | --- |
| id | SQLite | Генерируется при создании проекта; сохраняется при повторном импорте |
| name | ImportedProject.name | SMHome_UniversalRound_ESP32_C3_Mini_v4 |
| descr | ImportedProject.description | Smart home relay board. |
| plugin_id | Манифест выбранного плагина | org.partsdb.kicad |
| external_id | ImportedProject.external_id | 1a9f0d73-6986-450b-8da5-dca8d718cd0d |
| source_uri | URI, переданный приложением плагину | file:///Users/abel/Developing/PartsDB/tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro |
| last_imported_at | PartsDB | Время успешного сохранения в UTC; до первого успеха NULL |
| needs_reload | PartsDB | 0 после успешного сохранения; 1 при необходимости повторного импорта |
| properties_json | json.dumps(ImportedProject.properties, ensure_ascii=False) | Объект с source_files — списком трёх прочитанных схем |

Плагин передаёт имя, описание, внешний ID и свойства. PartsDB управляет
внутренним ID, выбором плагина, URI и служебными полями состояния импорта.
Сам `source_uri` не является полем `ImportedProject`: приложение знает его
из запроса на импорт.

## 5. Запись компонентов: PROJECT_COMPONENTS

Сохраняются 49 строк — одна строка на физическую позицию. Секции одной детали
объединяет плагин. Отдельного поля количества нет: потребность вычисляется
группировкой позиций.

Соответствие полей для C1:

| Поле БД | Источник | Значение / правило |
| --- | --- | --- |
| id | SQLite | Генерируется при добавлении позиции |
| project_id | PROJECTS.id | ID проекта в этой БД |
| external_id | component.external_id | /1a9f0d73-6986-450b-8da5-dca8d718cd0d/26ba38b8-de6a-4290-840f-c0381062839e/01b136d3-50db-47bc-9e3a-bd2417f28c2f |
| reference | component.reference | C1 |
| kind | component.kind | capacitor |
| value_raw | component.value_raw | 100nF |
| nominal_value | component.nominal.value либо NULL | 0.0000001 |
| nominal_unit | component.nominal.unit либо NULL | F |
| model | component.model | NULL |
| symbol_id | component.symbol_id | Device:C_Small |
| footprint | component.footprint | Capacitor_SMD:C_0805_2012Metric |
| description | component.description | Unpolarized capacitor, small symbol |
| in_bom | int(component.in_bom) | 1 |
| on_board | int(component.on_board) | 1 |
| dnp | int(component.dnp) | 0 |
| properties_json | json.dumps(component.properties, ensure_ascii=False) | Все исходные свойства C1 и UUID секций; см. пример JSON |

Правила преобразования:

- `nominal` раскладывается на `nominal_value` и `nominal_unit`; если `nominal`
  отсутствует, оба поля получают SQL `NULL`.
- Нормализованный номинал хранится десятичной строкой (`TEXT`), без преобразования
  в `float`. Исходное написание остаётся в `value_raw`.
- `None` преобразуется в SQL `NULL`; флаги — в целые `0` или `1`.
- `properties` сериализуется в JSON-текст с сохранением Unicode. Например,
  исходное свойство `comments: "6v"` остаётся в `properties_json`; отдельного
  подтверждённого поля напряжения компонента в этой таблице нет.
- `footprint` сохраняется полностью, включая имя библиотеки. Преобразование
  посадочного места в складской корпус выполняется при сопоставлении.
- На пару `(project_id, external_id)` действует ограничение уникальности.
  Внешний ID компонента и внешний ID проекта относятся к разным сущностям.

Пример подготовки параметров одной строки по правилам `ProjectRepository`:

```python
import json

row = {
    'project_id': project_id,  # PROJECTS.id, полученный приложением
    'external_id': component.external_id,
    'reference': component.reference,
    'kind': component.kind,
    'value_raw': component.value_raw,
    'nominal_value': component.nominal.value if component.nominal else None,
    'nominal_unit': component.nominal.unit if component.nominal else None,
    'model': component.model,
    'symbol_id': component.symbol_id,
    'footprint': component.footprint,
    'description': component.description,
    'in_bom': int(component.in_bom),
    'on_board': int(component.on_board),
    'dnp': int(component.dnp),
    'properties_json': json.dumps(component.properties, ensure_ascii=False),
}
```

Это иллюстрация преобразования данных; запросы записи находятся в `ElData/ElDBScheme.py`, SQLite-транзакции — в `ElData/ElDBConnect.py`, а `ElPluginMgr/repository.py` проверяет данные и делегирует сохранение.
SQL должен получать значения отдельными параметрами (`?` или `:name`),
без подстановки текста исходного проекта в SQL.

## 6. Сопоставления со складом: PROJECT_COMPONENT_MATCHES

Импортированные позиции сохраняются независимо от карточек склада `PARTS`.
При первичном импорте без подтверждённых сопоставлений эта таблица не получает
новых строк.

После выбора складской детали для C1 сохраняется:

| Поле | Содержание |
| --- | --- |
| `component_id` | Внутренний ID C1 из `PROJECT_COMPONENTS.id` |
| `part_id` | ID выбранной карточки конденсатора из `PARTS.id` |
| `needs_review` | `0` после подтверждения соответствия |
| `matched_at` | Время сопоставления в UTC; по умолчанию выставляет SQLite |

Конкретный `part_id` в примере не назначен: склад при подготовке документа
не анализировался. Одна позиция может иметь одно выбранное соответствие.
Список кандидатов не записывается как подтверждённое сопоставление.

Сам импорт не создаёт карточки `PARTS` и не списывает остатки. Например,
R1, R20 и R21 могут быть сопоставлены одной карточке резистора: потребность
составит три штуки, а позиции и обозначения сохранятся раздельно.

## 7. Порядок сохранения и повторный импорт

Сохранение выполняет PartsDB, а не плагин:

1. Получить и проверить весь результат импорта до изменения сохранённых данных:
   обязательные поля, уникальность внешних ID, допустимые флаги, сериализацию JSON.
2. Включить `PRAGMA foreign_keys = ON` на соединении до начала транзакции.
3. Начать одну транзакцию сохранения проекта и всех его позиций.
4. Создать или обновить `PROJECTS`, сохраняя ID существующего проекта.
5. Найти прежние позиции по `(project_id, external_id)`. Добавить новые,
   обновить существующие с сохранением их внутренних ID. Не применять
   `INSERT OR REPLACE`: удаление и повторная вставка могут потерять сопоставления.
6. Удалить исчезнувшие позиции; их сопоставления удаляются каскадно.
7. Сохранить сопоставления оставшихся позиций. Если изменились номинал, модель,
   корпус или другие требования, отметить соответствие `needs_review = 1`.
8. Записать время успешного импорта в `last_imported_at` и `needs_reload = 0`.
9. Зафиксировать транзакцию. При ошибке откатить её целиком: прежний успешный
   результат и время последнего успеха сохраняются.

Необходимо использовать транзакционный интерфейс соединения SQLite:
существующие вспомогательные методы, вызывающие `commit()` после каждого
запроса, не обеспечат атомарность всей операции импорта.

При обновлении или замене плагина проект отмечается `needs_reload = 1`.
Соответствие внешних ID при замене другим импортёром требует проверки:
совпадение внешней системы само по себе не гарантирует одинаковые ID компонентов.

## 8. Диагностика и исходники

`warnings` возвращается для показа или журнала выполнения. В текущей схеме
нет отдельного столбца предупреждений или таблицы истории попыток импорта.
Список исходных файлов сохраняется внутри `PROJECTS.properties_json`.

Источники контракта и реализации:

- [Модели публичного API](../ElPartsPluginApi/importers/models.py).
- [Импортёр KiCad](../ElPartsPluginSrc/kicad/partsdb_kicad/plugin.py).
- [Манифест плагина](../ElPartsPluginSrc/kicad/partsdb-plugin.json).
- [SQL-схема приложения](../ElData/ElDBScheme.py).
- [Описание схемы импорта](project-import-schema.md).
- [Структура БД для плагинов и деталей](database-plugins-and-parts.md).
- [Тесты плагина](../tests/kikad_plugin/test_importer.py).
