#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System Dependency Checker for AIGV Studio.
Checks Python version, pip packages, and external tools.
"""

from __future__ import absolute_import

import os
import shutil
import sys


def check_python():
    """Check Python version >= 3.10."""
    version = sys.version_info
    ok = version >= (3, 10)
    return {
        'name': 'Python',
        'version': '{0}.{1}.{2}'.format(version.major, version.minor, version.micro),
        'required': '>= 3.10',
        'status': 'OK' if ok else 'FAIL',
        'ok': ok,
    }


def check_pip_packages():
    """Check required pip packages."""
    packages = ['flask', 'werkzeug', 'requests', 'psutil']
    results = []
    for pkg in packages:
        required = pkg != 'psutil'
        try:
            __import__(pkg)
            results.append({
                'name': pkg, 'status': 'OK', 'ok': True, 'required': required,
            })
        except ImportError:
            results.append({
                'name': pkg, 'status': 'MISSING', 'ok': False, 'required': required,
            })
    return results


def check_tool(name, binary=None, required=False):
    """Check if an external tool is available in PATH."""
    tool_bin = binary or name
    available = shutil.which(tool_bin) is not None
    return {
        'name': name,
        'path': shutil.which(tool_bin) if available else None,
        'status': 'OK' if available else 'NOT FOUND',
        'ok': available,
        'required': required,
    }


def main():
    print("=" * 60)
    print("AIGV Studio - Dependency Check")
    print("=" * 60)
    print()

    all_ok = True

    # Python check
    py = check_python()
    print("[{0}] {1} {2} (required: {3})".format(
        py['status'], py['name'], py['version'], py['required']))
    if not py['ok']:
        all_ok = False
    print()

    # Pip packages
    print("Pip Packages:")
    pkgs = check_pip_packages()
    for pkg in pkgs:
        print("  [{0}] {1}{2}".format(
            pkg['status'], pkg['name'],
            '' if pkg.get('required', True) else ' [OPTIONAL]',
        ))
        if pkg.get('required', True) and not pkg['ok']:
            all_ok = False
    print()

    # External tools
    print("External Tools:")
    tools = [
        ('ffmpeg', None, True),
        ('ffprobe', None, True),
        ('piper', os.environ.get('PIPER_BIN') or None, False),
        ('fc-match', None, False),
        ('blender', None, False),
        ('nvidia-smi', None, False),
    ]
    for name, binary, required in tools:
        result = check_tool(name, binary, required=required)
        tag = " [REQUIRED]" if result.get('required') else " [OPTIONAL]"
        print("  [{0}] {1}{2} ({3})".format(
            result['status'], result['name'], tag, result['path'] or 'not found'))
        if result.get('required') and not result['ok']:
            all_ok = False
    print()

    # Data directory
    data_dir = os.environ.get('DATA_DIR', './data')
    if os.path.isdir(data_dir):
        print("[OK] Data directory: {0}".format(os.path.abspath(data_dir)))
    else:
        print("[WARN] Data directory not found: {0}".format(data_dir))

    model_path = os.environ.get(
        'PIPER_MODEL_PATH',
        os.path.join(data_dir, 'tts_models', 'zh_CN-huayan-medium.onnx'),
    )
    voices_path = os.environ.get(
        'TTS_VOICES_FILE', os.path.join(data_dir, 'tts_voices.json')
    )
    print("[{0}] Piper model: {1}".format(
        'OK' if os.path.isfile(model_path) else 'OPTIONAL/MISSING',
        model_path,
    ))
    print("[{0}] TTS voice registry: {1}".format(
        'OK' if os.path.isfile(voices_path) else 'OPTIONAL/MISSING',
        voices_path,
    ))

    print()
    print("=" * 60)
    if all_ok:
        print("All critical dependencies met.")
    else:
        print("Some critical dependencies are missing!")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
