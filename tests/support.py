# -*- coding: utf-8 -*-
"""Shared helpers for in-process Flask app tests."""
from __future__ import absolute_import

import os

from backend import asset_service, creative_project_service, prompt_doc_service
from backend import storyboard_service, task_service, timeline_service
from backend.auth_service import AuthService
from backend.config import Config
from backend.database import reset_database
from backend.rate_limiter import _rate_limiter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(ROOT, "data", "catalog", "knowledge_base.json")


def reset_globals():
    reset_database()
    asset_service._asset_service = None
    creative_project_service._creative_project_service = None
    storyboard_service._storyboard_service = None
    task_service._task_service = None
    timeline_service._timeline_service = None
    try:
        prompt_doc_service._prompt_doc_service = None
    except Exception:
        pass
    try:
        _rate_limiter._windows.clear()
    except Exception:
        pass


def make_app(tmp_path, **overrides):
    from app import create_app

    reset_globals()
    data_dir = str(tmp_path)

    class TestConfig(Config):
        APP_ENV = "test"
        IS_PRODUCTION = False
        DATA_DIR = data_dir
        JOBS_DIR = os.path.join(data_dir, "jobs")
        CATALOG_PATH = CATALOG_PATH
        SECRET_KEY = "test-secret-key-0123456789abcdef"
        DEMO_MODE = False
        ALLOW_REGISTRATION = True
        CSRF_ENABLED = True
        SESSION_SECURE = False
        SESSION_LIFETIME_DAYS = 1
        START_TASK_WORKER = False
        ENABLE_MONITORING_WORKER = False
        LOGIN_RATE_LIMIT = 1000
        REGISTER_RATE_LIMIT = 1000
        LOGIN_MAX_FAILURES = 3
        LOGIN_LOCKOUT_SECONDS = 60
        ARK_API_KEY = ""
        VOLCENGINE_API_KEY = ""
        ARK_IMAGE_MODEL = ""
        ARK_IMAGE_MODEL_FLASH = ""
        ARK_IMAGE_MODEL_LITE = ""
        ARK_VIDEO_MODEL = ""
        ARK_VIDEO_MODEL_20 = ""
        ARK_VIDEO_MODEL_10_PRO = ""
        CREDENTIAL_REQUIRE_HTTPS = False
        SEEDANCE_API_KEY = ""
        LUMA_API_KEY = ""
        LLM_API_KEY = ""
        OPENAI_API_KEY = ""
        OPENAI_BASE_URL = "https://api.openai.com/v1"
        OPENAI_IMAGE_MODEL = "gpt-image-1"
        CREDENTIAL_ENCRYPTION_KEY = ""
        ALLOW_INSECURE_PROVIDER_URLS = False
        COMFYUI_ENABLED = False
        COMFYUI_BASE_URL = ""
        PIPER_MODEL_PATH = ""
        VOLCENGINE_USAGE_ENABLED = False
        VOLCENGINE_BILLING_ENABLED = False
        VOLCENGINE_ACCESS_KEY_ID = ""
        VOLCENGINE_SECRET_ACCESS_KEY = ""
        VOLCENGINE_ARK_REGION = "cn-beijing"
        VOLCENGINE_BILLING_REGION = "cn-north-1"
        VOLCENGINE_ARK_PROJECT = "default"
        VOLCENGINE_USAGE_SYNC_ENABLED = False
        VOLCENGINE_BILLING_SYNC_ENABLED = False
        VOLCENGINE_USAGE_SYNC_INTERVAL_S = 1800
        VOLCENGINE_BILLING_SYNC_INTERVAL_S = 86400
        VOLCENGINE_USAGE_LOOKBACK_DAYS = 31
        VOLCENGINE_BILLING_LOOKBACK_MONTHS = 3
        VOLCENGINE_SYNC_TIMEOUT_S = 20
        VOLCENGINE_SYNC_MAX_RETRIES = 2
        VOLCENGINE_ARK_BILL_PRODUCT_FILTER = ""
        VOLCENGINE_ARK_BILL_SPLIT_DIMENSION = ""
        VOLCENGINE_ARK_API_KEY_RESOURCE_ID = ""

    for key, value in overrides.items():
        setattr(TestConfig, key, value)

    app = create_app(TestConfig)
    app.config["TESTING"] = True
    return app


def csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200, response.data
    return response.get_json()["data"]["csrf_token"]


def auth_headers(token):
    return {"X-CSRF-Token": token}


def register(client, username, password="password123", nickname=None, email=""):
    token = csrf(client)
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "confirm_password": password,
            "nickname": nickname or username,
            "email": email,
            "terms_accepted": True,
        },
        headers=auth_headers(token),
    )
    return response


def register_and_login(client, username, password="password123", nickname=None, email=""):
    response = register(client, username, password=password, nickname=nickname, email=email)
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    return data["user"], data["csrf_token"]


def login(client, username, password="password123"):
    token = csrf(client)
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers=auth_headers(token),
    )
    return response


def login_and_token(client, username, password="password123"):
    response = login(client, username, password)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    return data["user"], data["csrf_token"]


def create_admin(data_dir, username="rootadmin", password="AdminPass12345", email="admin@example.com"):
    service = AuthService(str(data_dir))
    return service.create_user(
        username=username,
        password=password,
        email=email,
        nickname="Root Admin",
        role="admin",
    )
