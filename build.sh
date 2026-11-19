#!/bin/bash
#
# Build script.
#   -u   regenerate UI and Qt resources (updateui.sh)
#   -t   run all unit tests recursively under tests/
#   -b   build the application with PyInstaller (dist/ElPartsDB)
#   -p   build the KiCad plugin wheel (dist/plugins/)
#   -a   regenerate UI, run tests, and build
#   -h   help
# Options can be combined: ./build.sh -tb runs tests then builds; -a runs the full pipeline.

cd "$(dirname "$0")" || exit 1

usage() {
    echo "Usage: $0 [-u] [-t] [-b] [-p] [-a] [-h]"
    echo "  -u   regenerate UI and Qt resources (updateui.sh)"
    echo "  -t   run all unit tests"
    echo "  -b   build the application (PyInstaller)"
    echo "  -p   build the KiCad plugin wheel (dist/plugins/)"
    echo "  -a   regenerate UI, run tests, then build"
    echo "  -h   show this help"
    echo "With -t, tests run before either build; builds start only if all tests pass."
}

RUN_UI=0
RUN_TESTS=0
RUN_BUILD=0
RUN_PLUGIN=0
while getopts ":utbpah" opt; do
    case "$opt" in
        u) RUN_UI=1 ;;
        t) RUN_TESTS=1 ;;
        b) RUN_BUILD=1 ;;
        p) RUN_PLUGIN=1 ;;
        a) RUN_UI=1; RUN_TESTS=1; RUN_BUILD=1 ;;
        h) usage; exit 0 ;;
        \?) echo "Unknown option: -$OPTARG" >&2; usage >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
if [ $# -gt 0 ]; then
    echo "Unexpected argument: $1" >&2; usage >&2; exit 2
fi
if [ $RUN_UI -eq 0 ] && [ $RUN_TESTS -eq 0 ] && [ $RUN_BUILD -eq 0 ] && [ $RUN_PLUGIN -eq 0 ]; then
    usage >&2; exit 2
fi

# Python of the project's virtual env (has PyQt6), else the one on PATH
if [ -x venv/bin/python ]; then
    PYTHON=venv/bin/python
else
    PYTHON=python3
fi

if [ $RUN_UI -eq 1 ]; then
    echo "=== Generate UI and Qt resources ==="
    ./updateui.sh || exit $?
fi

if [ $RUN_TESTS -eq 1 ]; then
    echo "=== Unit tests ==="
    # Qt widgets in the tests need no screen
    QT_QPA_PLATFORM=offscreen "$PYTHON" -m unittest discover -s tests -p 'test_*.py'
    status=$?
    if [ $status -ne 0 ]; then
        echo "=== Unit tests FAILED ===" >&2
        "$PYTHON" tools/cleanup_test_databases.py --failed || echo "Test backup rotation failed" >&2
        exit $status
    fi
    "$PYTHON" tools/cleanup_test_databases.py --success || exit $?
    echo "=== Unit tests passed ==="
fi

if [ $RUN_BUILD -eq 1 ]; then
    echo "=== Build ==="
    "$PYTHON" tools/translations.py --check --compile || exit $?
    # PyInstaller from the same Python as the app, so it bundles the venv's PyQt6 and other packages
    if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
        echo "PyInstaller is not installed for $PYTHON. Install it: $PYTHON -m pip install pyinstaller" >&2
        exit 1
    fi
    "$PYTHON" -m PyInstaller  -F --onefile --windowed  -y  --clean --name="ElPartsDB" --icon="icons/ElPartsCatalog.icns" --add-data="translations:translations" --add-data="ElPartsPluginApi:ElPartsPluginApi" --add-data="ElPluginMgr:ElPluginMgr" main.py || exit $?
fi

if [ $RUN_PLUGIN -eq 1 ]; then
    echo "=== Build KiCad plugin ==="
    # Build from local sources using the existing environment, without network access.
    "$PYTHON" -m pip wheel --no-deps --no-build-isolation --no-index --no-cache-dir \
        --wheel-dir "$PWD/dist/plugins" ./ElPartsPluginSrc/kicad || exit $?
fi

#pyinstaller --windowed --name="Hello World" --iconpwd="Hello World.icns" --add-data="icons/hand.png:icons" --add-data="icons/lightning.png:icons" app.py
#--onefile
