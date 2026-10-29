# -*- coding: utf-8 -*-
"""
Tests for authentication security: rate limiting, lockout, password change.
"""
from __future__ import absolute_import

import json
import os
import sys
import time

import pytest
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.auth_service import AuthError, AuthService
from backend.config import Config
from backend.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_allows_requests_within_limit(self):
        """Test that requests within the limit are allowed."""
        limiter = RateLimiter()
        for i in range(5):
            allowed, retry = limiter.check_rate_limit('test-key', 10, 60)
            assert allowed is True
            assert retry == 0

    def test_blocks_after_limit(self):
        """Test that requests are blocked after limit exceeded."""
        limiter = RateLimiter()
        max_req = 3
        for i in range(max_req):
            allowed, _ = limiter.check_rate_limit('test-key-2', max_req, 60)
            assert allowed is True
        # Next request should be blocked
        allowed, retry = limiter.check_rate_limit('test-key-2', max_req, 60)
        assert allowed is False
        assert retry > 0

    def test_different_keys_independent(self):
        """Test that different keys have independent limits."""
        limiter = RateLimiter()
        # Fill up key-1
        for i in range(3):
            limiter.check_rate_limit('key-1', 3, 60)
        # key-2 should still be allowed
        allowed, _ = limiter.check_rate_limit('key-2', 3, 60)
        assert allowed is True

    def test_usage_count(self):
        """Test usage count tracking."""
        limiter = RateLimiter()
        for i in range(5):
            limiter.check_rate_limit('usage-key', 10, 60)
        count = limiter.get_usage('usage-key', 60)
        assert count == 5


class TestPasswordSecurity:
    """Test password hashing and change."""

    def test_password_hash_verification(self):
        """Test that password hashing works correctly."""
        password = 'test-password-123'
        hashed = generate_password_hash(password)
        assert check_password_hash(hashed, password) is True
        assert check_password_hash(hashed, 'wrong-password') is False

    def test_password_minimum_length(self, tmp_path):
        """The configured minimum is 8 and shorter passwords are rejected."""
        service = AuthService(str(tmp_path), Config())
        assert service.password_min >= 8
        with pytest.raises(AuthError) as exc:
            service.validate_password("1234567", "user")
        assert exc.value.code == "weak_password"
        assert service.validate_password("12345678", "user") == "12345678"
