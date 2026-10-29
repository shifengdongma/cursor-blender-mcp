# -*- coding: utf-8 -*-
"""Test configuration and fixtures for AIGV Studio tests."""
from __future__ import absolute_import

import os
import tempfile

import pytest

# Force an isolated test data dir and never load the developer's .env/provider keys.
os.environ["AIGV_ENV"] = "test"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="aigv_test_")
for _key in (
    "SECRET_KEY", "ARK_API_KEY", "VOLCENGINE_API_KEY", "SEEDANCE_API_KEY",
    "LUMA_API_KEY", "LLM_API_KEY", "ALIYUN_ACCESS_KEY", "TENCENT_SECRET_ID",
):
    os.environ.pop(_key, None)

from backend.database import get_database, reset_database
from backend.config import Config


@pytest.fixture
def test_db():
    """Provide a fresh in-memory database for each test."""
    # Reset global DB instance
    reset_database()
    # Create temp dir
    tmpdir = tempfile.mkdtemp(prefix="aigv_test_db_")
    db_path = os.path.join(tmpdir, "test.db")
    db = get_database(db_path)
    yield db
    db.close()
    reset_database()


@pytest.fixture
def test_config():
    """Provide test configuration with empty API keys."""
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
    os.environ["LLM_MODEL_NAME"] = "gpt-4o"
    os.environ["COMFYUI_BASE_URL"] = "http://127.0.0.1:8188"
    os.environ["PIPER_BIN"] = "piper"
    os.environ["PIPER_MODEL_PATH"] = "./data/tts_models/test.onnx"
    os.environ["FFMPEG_BIN"] = "ffmpeg"
    os.environ["FFPROBE_BIN"] = "ffprobe"
    cfg = Config()
    yield cfg


@pytest.fixture
def app(tmp_path):
    """Real create_app() instance with an isolated data directory."""
    from tests.support import make_app, reset_globals
    application = make_app(tmp_path)
    yield application
    reset_globals()


@pytest.fixture
def client(app):
    return app.test_client()
