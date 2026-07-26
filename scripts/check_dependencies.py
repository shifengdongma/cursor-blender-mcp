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
        try:
            __import__(pkg)
            results.append({'name': pkg, 'status': 'OK', 'ok': True})
        except ImportError:
            results.append({'name': pkg, 'status': 'MISSING', 'ok': False})
    return results


def check_tool(name, binary=None):
    """Check if an external tool is available in PATH."""
    tool_bin = binary or name
    available = shutil.which(tool_bin) is not None
    return {
        'name': name,
        'path': shutil.which(tool_bin) if available else None,
        'status': 'OK' if available else 'NOT FOUND',
        'ok': True,  # optional tools are non-critical
        'required': name in ('ffmpeg', 'ffprobe'),
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
        print("  [{0}] {1}".format(pkg['status'], pkg['name']))
        if not pkg['ok']:
            all_ok = False
    print()

    # External tools
    print("External Tools:")
    tools = [
        ('blender', None),
        ('ffmpeg', None),
        ('ffprobe', None),
        ('nvidia-smi', None),
    ]
    for name, binary in tools:
        result = check_tool(name, binary)
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
