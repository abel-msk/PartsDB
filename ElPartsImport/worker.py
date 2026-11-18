"""Standalone worker copied alongside the SDK into each plugin environment."""
from pathlib import Path
import sys

# -I isolates the interpreter; only this copied runtime is added explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contextlib import redirect_stdout
from dataclasses import asdict
import importlib
import json
import traceback

from ElPartsPluginApi.importers import PluginError, ProjectImporter
from ElPartsPluginApi.importers.context import ImportContext
from ElPartsPluginApi.importers.manifest import PluginManifest
from ElPartsImport.protocol import (PROTOCOL_VERSION, MAX_MESSAGE_BYTES, json_text,
                                    project_to_dict, validate_formats)


def emit(event):
    event = dict(event, protocol_version=PROTOCOL_VERSION)
    line = json_text(event)
    if len(line.encode('utf-8')) > MAX_MESSAGE_BYTES:
        raise PluginError('Plugin message exceeds the size limit')
    sys.__stdout__.write(line + '\n')
    sys.__stdout__.flush()


def main():
    try:
        line = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if len(line) > MAX_MESSAGE_BYTES:
            raise PluginError('Request exceeds the size limit')
        request = json.loads(line)
        if request.get('protocol_version') != PROTOCOL_VERSION:
            raise PluginError('Incompatible worker protocol')
        manifest = PluginManifest.from_dict(request['manifest'])
        module, name = manifest.entry_point.split(':')
        with redirect_stdout(sys.stderr):
            cls = getattr(importlib.import_module(module), name)
            if not isinstance(cls, type) or not issubclass(cls, ProjectImporter):
                raise PluginError('Entry point must implement ProjectImporter')
            importer = cls()
            importer.context = ImportContext(emit=emit)
            if request['action'] == 'inspect':
                result = validate_formats([asdict(f) for f in importer.get_import_formats()])
            elif request['action'] == 'import':
                importer.context.progress(0, None, 'Reading project')
                result = project_to_dict(importer.import_project(request['source_uri']))
                importer.context.progress(1, 1, 'Project read')
            else:
                raise PluginError('Unknown worker action')
        emit({'type': 'result', 'result': result})
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit({'type': 'error', 'error_type': type(exc).__name__, 'message': str(exc)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
