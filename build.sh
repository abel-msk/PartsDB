#!/bin/bash
#
# Build script.
#   -t   run all unit tests (tests/test_*.py)
#   -b   build the application with PyInstaller (dist/ElPartsDB)
#   -h   help
# Options can be combined: ./build.sh -t -b (or -tb) runs the tests first and builds only if they pass.

cd "$(dirname "$0")" || exit 1

usage() {
    echo "Usage: $0 [-t] [-b] [-h]"
    echo "  -t   run all unit tests"
    echo "  -b   build the application (PyInstaller)"
    echo "  -h   show this help"
    echo "With -t and -b together the tests run first; the build starts only if all tests pass."
}

RUN_TESTS=0
RUN_BUILD=0
while getopts ":tbh" opt; do
    case "$opt" in
        t) RUN_TESTS=1 ;;
        b) RUN_BUILD=1 ;;
        h) usage; exit 0 ;;
        \?) echo "Unknown option: -$OPTARG" >&2; usage >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
if [ $# -gt 0 ]; then
    echo "Unexpected argument: $1" >&2; usage >&2; exit 2
fi
if [ $RUN_TESTS -eq 0 ] && [ $RUN_BUILD -eq 0 ]; then
    usage >&2; exit 2
fi

# Python of the project's virtual env (has PyQt6), else the one on PATH
if [ -x venv/bin/python ]; then
    PYTHON=venv/bin/python
else
    PYTHON=python3
fi

if [ $RUN_TESTS -eq 1 ]; then
    echo "=== Unit tests ==="
    # Qt widgets in the tests need no screen
    QT_QPA_PLATFORM=offscreen "$PYTHON" -m unittest discover -s tests -p 'test_*.py'
    status=$?
    if [ $status -ne 0 ]; then
        echo "=== Unit tests FAILED ===" >&2
        exit $status
    fi
    echo "=== Unit tests passed ==="
fi

if [ $RUN_BUILD -eq 1 ]; then
    echo "=== Build ==="
    # PyInstaller from the same Python as the app, so it bundles the venv's PyQt6 and other packages
    if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
        echo "PyInstaller is not installed for $PYTHON. Install it: $PYTHON -m pip install pyinstaller" >&2
        exit 1
    fi
    "$PYTHON" -m PyInstaller  -F --onefile --windowed  -y  --clean --name="ElPartsDB" --icon="icons/ElPartsCatalog.icns" main.py || exit $?
fi

#pyinstaller --windowed --name="Hello World" --iconpwd="Hello World.icns" --add-data="icons/hand.png:icons" --add-data="icons/lightning.png:icons" app.py
#--onefile
