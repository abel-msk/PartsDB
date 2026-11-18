"""Public importer failures; a failed import must not replace stored data."""


class PluginError(Exception):
    pass


class UnsupportedFormatError(PluginError):
    pass


class InvalidSourceError(PluginError):
    pass


class MissingSourceError(PluginError):
    pass


class ImportCancelled(PluginError):
    pass
