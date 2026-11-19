"""Stable plugin type identifiers shared by the application and plugin authors."""

PLUGIN_TYPE_IMPORT = 'project_import'
PLUGIN_TYPE_PARTS_ORDER = 'parts_order'
PLUGIN_TYPE_SHIPMENT_TRACKING = 'shipment_tracking'

PLUGIN_TYPES = frozenset((PLUGIN_TYPE_IMPORT, PLUGIN_TYPE_PARTS_ORDER,
                          PLUGIN_TYPE_SHIPMENT_TRACKING))
