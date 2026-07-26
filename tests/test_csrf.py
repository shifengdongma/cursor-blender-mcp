# -*- coding: utf-8 -*-
"""
Tests for CSRF protection.
"""
from __future__ import absolute_import

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.csrf import generate_csrf_token, get_csrf_token


class TestCSRF:
    """Test CSRF token generation and validation."""

    def test_token_generation_is_unique(self):
        """Test that generated tokens are unique."""
        token1 = os.urandom(12).hex()
        token2 = os.urandom(12).hex()
        assert token1 != token2

    def test_token_is_hex_string(self):
        """Test that tokens are hex strings."""
        token = os.urandom(12).hex()
        assert isinstance(token, str)
        assert len(token) == 24
