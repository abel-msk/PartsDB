"""Configured log severity and destinations apply to modules registered after startup."""
import io
import logging
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import ElCommon


class DebugLoggingTests(unittest.TestCase):
    """Verify console/file diagnostics and inheritance of the selected logging severity."""

    def test_late_module_debug_records_reach_console_and_file(self):
        """Retain DEBUG for modules loaded after the main logging setup.

        @return [None] Verify one diagnostic reaches both configured handlers.
        """
        console = io.StringIO()
        handler = logging.StreamHandler(console)
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.multiple(ElCommon, loggers={}, handlers=[handler], def_level=None), \
                mock.patch.object(ElCommon.logging, 'getLogger', side_effect=logging.Logger), \
                mock.patch('sys.stdout', new=io.StringIO()):
            ElCommon.setLevel(logging.DEBUG)
            filename = Path(folder)/'debug.log'
            ElCommon.setLogFile(str(filename))
            try:
                logger = ElCommon.setLogger('late.test.module')
                logger.debug('Matching progress: %s/%s', 1, 2)
                self.assertIn('Matching progress: 1/2', console.getvalue())
                self.assertIn('Matching progress: 1/2', filename.read_text())
            finally:
                for output in ElCommon.handlers[1:]:
                    output.close()

    def test_late_module_respects_non_debug_level(self):
        """Avoid forcing DEBUG for a module created under a quieter configuration.

        @return [None] Verify existing and newly registered modules share WARNING.
        """
        with mock.patch.multiple(ElCommon, loggers={}, handlers=[], def_level=None), \
                mock.patch.object(ElCommon.logging, 'getLogger', side_effect=logging.Logger):
            first = ElCommon.setLogger('first.test.module')
            ElCommon.setLevel(logging.WARNING)
            late = ElCommon.setLogger('late.test.module')
            self.assertEqual(first.level, logging.WARNING)
            self.assertEqual(late.level, logging.WARNING)
            self.assertFalse(late.isEnabledFor(logging.DEBUG))
