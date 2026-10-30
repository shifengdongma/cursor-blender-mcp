# -*- coding: utf-8 -*-
"""Thread-local requests sessions for safe connection reuse.

Each worker thread gets its own Session, so provider credentials or mutable
headers are never shared across threads.  Callers must still pass per-request
headers explicitly.
"""
from __future__ import absolute_import

import threading

import requests

_local = threading.local()


def get_session():
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        _local.session = session
    return session


def close_session():
    session = getattr(_local, "session", None)
    if session is not None:
        try:
            session.close()
        finally:
            _local.session = None
