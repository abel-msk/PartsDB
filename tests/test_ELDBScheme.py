import os
from asyncio import events
from unittest import TestCase

from ElDBScheme import DBFactory, Types

DBNAME = "./test_db.sqlite"
EL_NAME1 = "Диод"
EL_NAME2 = "Резистор"
EL_NAME12 = "шотки"
EL_NAME13 = "test"
PATH = EL_NAME1 + " " + EL_NAME12


class TestDBFactory(TestCase):
    # def __init__(self, methodName='runTest'):
    #     super(TestDBFactory, self).__init__(methodName)
    #     self.factory
    # factory = None

    # def setUpModule(self):
    def setUp(self):

        if os.path.exists(DBNAME):
            os.remove(DBNAME)
        self.factory = DBFactory(DBNAME)
        # self.factory.createDB()

        self.factory.createTypeByPath(EL_NAME1)
        el_type2 = self.factory.createTypeByPath(EL_NAME2)
        self.factory.createTypeByPath(PATH)

    def test_get_root_types(self):
        list: Types = self.factory.getRootTypes()
        for t in list:
            print("Element name: {}, path: {}".format(t.name, t.path))
        self.assertEqual(list[0].name, EL_NAME1)
        self.assertEqual(list[1].name, EL_NAME2)

    def test_get_typeByPath(self):
        theType = self.factory.getTypeByPath(PATH)
        self.assertEqual(theType.name, EL_NAME12, "Looking for path: {}, Found obj path: {}".format(PATH, theType.path))

    def test_create_element(self):
        theType = self.factory.getTypeByPath(EL_NAME2)
        el = {
            "part_num": "SCP12",
            "value": "10",  # Номинал
            "units": "A",  # Eдиницы измерения
            "reduced_val": "10",  # Приведенное к единой размерности значнеие
            "reduced_val_units": "A",  # Единицы измерения для приведенного к единой размерности значнеия
            "chip_label": "gt",  # Обозначение на чипе
            "max_current": "1",  # Максимально допустимый ток
            "max_voltage": "0.5",  # Максимально допустимое напряжение
            "description": "Resistor",  # Описание
            "present": "BOOL",  # В наличии
            "quantity": "100",  # Количество
            "price": "0,95",  # Цена за единицу
            "currency": "RUB"
        }

        el = self.factory.createPart(theType, el)
        element_id = el.id
        self.assertEqual(el.part_num, "SCP12")
        el["part_num"] = "SCP12TEST"
        el.save()

        el = self.factory.loadElementById(element_id)
        self.assertEqual(el.part_num, "SCP12TEST")

    def test_header(self):
        label = "Номинал"
        theType = self.factory.getTypeByPath(EL_NAME2)

        headers = theType.getHeaders()
        header = headers["part_num"]
        header.display = "PART_NUMBER"
        header.hidden = "FALSE"
        header.label = label
        header.save()

        theType = self.factory.getTypeByPath(EL_NAME2)
        hdrs2 = theType.getHeaders()
        self.assertEqual(hdrs2["part_num"].display, "PART_NUMBER")
        self.assertGreaterEqual(hdrs2["part_num"].id, 0,  "ID={}".format(hdrs2["part_num"].id))

    def tearDown(self):
        self.factory.disconnect()



