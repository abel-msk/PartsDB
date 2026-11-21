# Импортёр KiCad: поведение и результат API

Актуальность: 21 ноября 2026. Пакет **0.1.0**, публичный API **1**.
Этот документ описывает чтение KiCad и Python-модели, возвращаемые импортёром.

- [Общий контракт плагинов](plugin-architecture-and-api.md).
- [Установка и запуск](plugin-runtime.md).
- [Единый справочник таблиц и пример записи результата](database-schema.md#пример-преобразования-результата-api-в-строки-бд).
- [Миграции базы приложения](database-migrations.md).

Плагин не открывает SQLite и не знает схему хранения. За запись подтверждённого
результата отвечает PartsDB. Описания полей таблиц и соответствия моделям находятся
в справочнике таблиц по ссылке выше.

## Возможности и ограничения

Основной метод — `KiCadImporter.get_components(source_uri) -> list[ImportedComponent]`.
Принимает путь или локальный `file:` URI файла `.kicad_pro` либо `.kicad_sch`.
Для проекта читает одноимённую корневую схему и рекурсивно связанные листы.
Не требует запуска KiCad, Qt, подключения к SQLite или внешних Python-зависимостей.

Из корня PartsDB:

```sh
PYTHONPATH=ElPartsPluginSrc/kicad:. python3 - <<'PY'
from partsdb_kicad import KiCadImporter

source = 'tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro'
components = KiCadImporter().get_components(source)
for component in components:
    print(component.reference, component.kind, component.value_raw, component.footprint)
PY
```

Одна запись соответствует одной физической позиции. Секции многосекционного
символа объединяются; повторные экземпляры листов различаются по пути UUID.
Внешний ID состоит из пути экземпляра листа и UUID символа первой секции.
Переименование обозначения не меняет ID. Служебные символы питания и библиотечные
шаблоны исключаются. Позиции с `in_bom=False`, `on_board=False` и `dnp=True`
возвращаются с исходными флагами, чтобы приложение могло выбрать фильтрацию.

Возвращаются исходное значение, нормализованный номинал R/C/L, категория,
модель, библиотечный символ, посадочное место, описание, пользовательские
свойства и UUID секций. Категория определяется по библиотеке и имени символа,
затем по обозначению; это подсказка для сопоставления, а не проверка параметров
детали. Нераспознанный номинал остаётся `None`, исходный текст сохраняется.

`import_project(source_uri)` возвращает `ImportedProject`: название, внешний
UUID, компоненты, предупреждения и прочитанные файлы в `properties['source_files']`.
`probe(source_uri)` проверяет корневой источник; полный обход выполняется при
импорте. Отсутствующий дочерний лист, цикл, повреждённый файл, неоднозначные или
незаполненные обозначения вызывают стандартное исключение API. Частичный список
при ошибке не возвращается.

Поддерживается современный S-expression формат схем с UUID. Старые `.sch`,
HTTP/HTTPS и произвольные переменные путей листов пока не поддерживаются.
В путях листов разрешается `${KIPRJMOD}`. API предоставляет PartsDB через
`ElPartsPluginApi`; пакет плагина содержит манифест `partsdb-plugin.json`.
Установка через менеджер, запуск в отдельном процессе, предпросмотр и сохранение
в БД реализованы. Плагин также можно вызывать непосредственно из Python.
См. [инструкцию установки и запуска](plugin-runtime.md).

## Источники и вызов

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

## Пример результата API

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

## Полный перечень возвращённых позиций

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

## Сборка и проверки

Из корня репозитория: `./build.sh -p` создаёт wheel в `dist/plugins`;
`./build.sh -tp` сначала выполняет полный прогон тестов.
[Команды локального запуска и сборки](../ElPartsPluginSrc/kicad/README.md).

Пример результата выше относится к тестовому проекту репозитория: 49 физических
позиций в трёх связанных схемах. `warnings` возвращается для предпросмотра или
журнала; `properties['source_files']` перечисляет прочитанные файлы.

Исходники:

- [Реализация импортёра](../ElPartsPluginSrc/kicad/partsdb_kicad/plugin.py).
- [Манифест](../ElPartsPluginSrc/kicad/partsdb-plugin.json).
- [Модели публичного API](../ElPartsPluginApi/importers/models.py).
- [Тесты импортёра](../tests/kikad_plugin/test_importer.py).
