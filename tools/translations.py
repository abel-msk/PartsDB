#!/usr/bin/env python3
"""Update Qt TS catalogs and compile QM files. Works with Python 3.11+ (including 3.14)."""
import argparse
import ast
from collections import Counter
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "translations"
FORMS = ("ElPartsMain.ui", "AppsPathSetup.ui", "ElOpenFileWnd.ui", "ElHdrEditWnd.ui", "ElPluginsWnd.ui", "ElUnitsWnd.ui")


def messages():
    """Extract literal translate()/QT_TRANSLATE_NOOP() calls and Designer strings.

    pylupdate6 6.10.0 uses ast.Str, removed in Python 3.14. This small extractor
    supports our explicit-context calls using ast.Constant, without patching PyQt.
    """
    result = set()
    # UI controllers also live in ElPluginMgr; plugin sources and tests are not scanned.
    sources = (list(ROOT.glob("*.py")) + list((ROOT / "ElPluginMgr").rglob("*.py"))
               + list((ROOT / "ElData").rglob("*.py")))
    for path in sorted(sources):
        if path.name in ("resources.py", "ElParts.py", "ElAppPathWnd.py", "ElOpenFileWnd.py", "ElHdrEditWnd.py", "ElPluginsWnd.py", "ElUnitsWnd.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name not in ("translate", "QT_TRANSLATE_NOOP") or len(node.args) < 2:
                continue
            args = node.args[:2]
            if all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in args):
                result.add((args[0].value, args[1].value))
    for filename in FORMS:
        form = ET.parse(ROOT / "qt" / filename).getroot()
        context = form.findtext("class")
        for string in form.iter("string"):
            if string.get("notr") != "true" and string.text:
                result.add((context, string.text))
    return result


def catalogMessages(path):
    return {(context.findtext("name"), msg.findtext("source")): msg
            for context in ET.parse(path).findall("context") for msg in context.findall("message")}


def update():
    DIRECTORY.mkdir(exist_ok=True)
    for language in ("en", "ru"):
        path = DIRECTORY / ("partsdb_" + language + ".ts")
        existing = catalogMessages(path) if path.exists() else {}
        root = ET.Element("TS", version="2.1", language=language, sourcelanguage="en")
        contexts = {}
        for key in sorted(messages()):
            context, source = key
            if context not in contexts:
                contexts[context] = ET.SubElement(root, "context")
                ET.SubElement(contexts[context], "name").text = context
            message = ET.SubElement(contexts[context], "message")
            ET.SubElement(message, "source").text = source
            old = existing.get(key)
            if language == "en":
                ET.SubElement(message, "translation").text = source
            elif old is not None and old.find("translation") is not None:
                message.append(old.find("translation"))
            else:
                ET.SubElement(message, "translation", type="unfinished")
        ET.indent(root, space="  ")
        path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
                        + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")


def check():
    expected = messages()
    for language in ("en", "ru"):
        path = DIRECTORY / ("partsdb_" + language + ".ts")
        actual = catalogMessages(path)
        if actual.keys() != expected:
            raise RuntimeError("{} is outdated; run tools/translations.py --update".format(path.name))
        for (_, source), message in actual.items():
            translation = message.find("translation")
            if translation is None or not translation.text or translation.get("type") == "unfinished":
                raise RuntimeError("Missing {} translation: {!r}".format(language, source))
            placeholders = r"\{(?:[A-Za-z_]\w*|\d*)\}"
            if Counter(re.findall(placeholders, source)) != Counter(re.findall(placeholders, translation.text)):
                raise RuntimeError("Changed format placeholders in {}: {!r}".format(language, source))


def compileCatalogs():
    from PyQt6.QtCore import QLibraryInfo
    binary = "lrelease.exe" if os.name == "nt" else "lrelease"
    candidates = [Path(sys.executable).parent / binary,
                  Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.BinariesPath)) / binary]
    executable = next((str(path) for path in candidates if path.is_file()), None)
    executable = executable or shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    if executable is None:
        raise RuntimeError("Install Qt Linguist tools (lrelease) and add them to PATH to compile translations.")
    for path in sorted(DIRECTORY.glob("partsdb_*.ts")):
        subprocess.run([executable, str(path), "-qm", str(path.with_suffix(".qm"))], check=True)
    standard = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_ru.qm"
    if not standard.is_file():
        raise RuntimeError("Qt's qtbase_ru.qm is missing from the PyQt6 installation.")
    shutil.copyfile(standard, DIRECTORY / standard.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="extract/update translation sources")
    parser.add_argument("--check", action="store_true", help="check catalogs for missing translations")
    parser.add_argument("--compile", action="store_true", help="compile catalogs using Qt lrelease")
    args = parser.parse_args()
    try:
        if args.update:
            update()
        if args.check or args.compile:
            check()
        if args.compile:
            compileCatalogs()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
