# -*- coding: utf-8 -*-
"""Run syntax checks and pure-JS unit tests when Node.js is available."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODE_CHECK_FILES = [
    "web/assets.js",
    "web/content-audit-core.js",
    "web/content-audit.js",
]

NODE_TEST_FILES = [
    "tests/js/content_audit.test.js",
]


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    return node


def test_javascript_syntax():
    node = _node()
    for rel_path in NODE_CHECK_FILES:
        result = subprocess.run(
            [node, "--check", rel_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "{0}\n{1}".format(
            rel_path, result.stderr or result.stdout
        )


def test_javascript_unit_tests():
    node = _node()
    for rel_path in NODE_TEST_FILES:
        result = subprocess.run(
            [node, rel_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "{0}\n{1}".format(
            rel_path, result.stderr or result.stdout
        )
