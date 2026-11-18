"""Run plugin code in its interpreter; cancellation never writes project data."""
from pathlib import Path
import json
import os
import signal
import queue
import subprocess
import threading
import time

from ElPartsPluginApi.importers import (
    ImportCancelled, InvalidSourceError, MissingSourceError, PluginError, UnsupportedFormatError,
)
from .protocol import (MAX_MESSAGE_BYTES, PROTOCOL_VERSION, json_text,
                       project_from_dict, validate_formats)


class PluginRunner:
    def __init__(self, timeout=120):
        self.timeout = timeout

    def run(self, plugin, source_uri='', action='import', cancel=None, on_event=None):
        if not plugin.enabled:
            raise PluginError('Plugin is disabled')
        cancel = cancel or threading.Event()
        if cancel.is_set():
            raise ImportCancelled('Import cancelled')
        python = plugin.python
        request = {'protocol_version': PROTOCOL_VERSION, 'manifest': plugin.manifest.to_dict(),
                   'action': action, 'source_uri': source_uri}
        process = subprocess.Popen([str(python), '-X', 'utf8', '-I', str(plugin.path / 'runtime/worker.py')],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=plugin.path, bufsize=0, start_new_session=os.name != 'nt')
        messages = queue.Queue(maxsize=256)
        diagnostic = []
        diagnostic_size = [0]

        def read_output():
            try:
                while True:
                    line = process.stdout.readline(MAX_MESSAGE_BYTES + 1)
                    if not line:
                        break
                    if len(line) > MAX_MESSAGE_BYTES:
                        messages.put(PluginError('Plugin message exceeds the size limit'))
                        break
                    messages.put(line)
            finally:
                messages.put(None)

        def read_errors():
            while True:
                chunk = process.stderr.read(4096)
                if not chunk:
                    return
                if diagnostic_size[0] < 1024 * 1024:
                    diagnostic.append(chunk)
                    diagnostic_size[0] += len(chunk)

        output_thread = threading.Thread(target=read_output, daemon=True)
        error_thread = threading.Thread(target=read_errors, daemon=True)
        output_thread.start()
        error_thread.start()
        deadline = time.monotonic() + self.timeout
        result = None
        received = False
        failure = None
        entries = [f'{action}: {plugin.manifest.name} {plugin.manifest.version}']
        try:
            encoded = (json_text(request) + '\n').encode('utf-8')
            process.stdin.write(encoded)
            process.stdin.close()
            while True:
                if cancel.is_set():
                    raise ImportCancelled('Import cancelled')
                if time.monotonic() >= deadline:
                    raise PluginError('Plugin execution timed out')
                try:
                    message = messages.get(timeout=0.05)
                except queue.Empty:
                    continue
                if message is None:
                    break
                if isinstance(message, Exception):
                    raise message
                try:
                    event = json.loads(message)
                except (ValueError, UnicodeError) as exc:
                    raise PluginError('Invalid worker JSON') from exc
                if not isinstance(event, dict) or event.get('protocol_version') != PROTOCOL_VERSION:
                    raise PluginError('Invalid worker protocol')
                event_type = event.get('type')
                if event_type == 'result':
                    if received:
                        raise PluginError('Worker returned multiple results')
                    result = event['result']
                    received = True
                elif event_type == 'error':
                    failure = event
                elif event_type in ('log', 'progress'):
                    if event_type == 'log' and len(entries) < 1000:
                        entries.append(str(event.get('message', ''))[:4096])
                    if on_event:
                        on_event(event)
                else:
                    raise PluginError('Unknown worker event')
            # The process may close stdout before finishing. Keep timeout/cancel active.
            while process.poll() is None:
                if cancel.is_set():
                    raise ImportCancelled('Import cancelled')
                if time.monotonic() >= deadline:
                    raise PluginError('Plugin execution timed out')
                time.sleep(0.02)
            if cancel.is_set():
                raise ImportCancelled('Import cancelled')
            if failure:
                errors = {c.__name__: c for c in (ImportCancelled, InvalidSourceError,
                          MissingSourceError, UnsupportedFormatError)}
                raise errors.get(failure.get('error_type'), PluginError)(failure.get('message', 'Plugin failed'))
            if process.returncode or not received:
                raise PluginError(f'Plugin exited without a valid result (code {process.returncode})')
            entries.append('Completed successfully')
            return project_from_dict(result) if action == 'import' else validate_formats(result)
        except (OSError, KeyError, TypeError) as exc:
            raise PluginError(f'Worker communication failed: {exc}') from exc
        finally:
            def stop_group(sig):
                if os.name != 'nt':
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    process.terminate() if sig == signal.SIGTERM else process.kill()

            # Also stop helpers that inherited pipes, even if the worker already exited.
            stop_group(signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            stop_group(getattr(signal, 'SIGKILL', signal.SIGTERM))
            process.wait()
            # Drain queued output so the reader can finish even after cancellation.
            while output_thread.is_alive():
                try:
                    messages.get(timeout=0.05)
                except queue.Empty:
                    pass
            error_thread.join(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
            self._log(plugin, '\n'.join(entries) + '\n' + b''.join(diagnostic).decode('utf-8', errors='replace'))

    @staticmethod
    def _log(plugin, text):
        if not text:
            return
        path = plugin.path / 'plugin.log'
        try:
            if path.exists() and path.stat().st_size > 1024 * 1024:
                path.replace(path.with_suffix('.log.old'))
            with path.open('a', encoding='utf-8') as stream:
                stream.write(text + '\n')
        except OSError:
            pass  # Logging must not turn a successful import into an error.
