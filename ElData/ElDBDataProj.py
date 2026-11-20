"""Data access for persisted project table layout preferences."""


def columnWidths(factory, table_name):
    """Read saved minimum widths. @param factory [DBFactory]; table_name [str] table identifier."""
    return factory.scheme.loadProjectColumnWidths(table_name)


def saveColumnWidths(factory, table_name, widths):
    """Save user widths. @param factory [DBFactory]; table_name [str]; widths [dict[str,int]] positive pixels."""
    factory.scheme.saveProjectColumnWidths(table_name, widths)
