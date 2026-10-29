#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Operator-only password recovery CLI.

This is intentionally not exposed through the web admin UI.  It increments the
user's session_version so existing sessions are revoked.
"""
from __future__ import absolute_import

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.auth_service import AuthError, AuthService
from backend.database import get_database


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reset an AIGV Studio user's password (operator CLI).")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--username", help="account username")
    args = parser.parse_args(argv)

    os.environ.setdefault("DATA_DIR", args.data_dir)
    get_database(os.path.join(args.data_dir, "aigv.db"))
    service = AuthService(args.data_dir)

    username = args.username or input("用户名: ").strip()
    row = service.get_user_by_username(username)
    if not row:
        print("用户不存在: {0}".format(username), file=sys.stderr)
        return 2

    password = getpass.getpass("新密码: ")
    confirm = getpass.getpass("再次输入新密码: ")
    if password != confirm:
        print("两次输入的密码不一致。", file=sys.stderr)
        return 2
    try:
        service.reset_password_for_user(row["id"], password)
    except AuthError as exc:
        print("重置失败: {0}".format(exc.message), file=sys.stderr)
        return 2
    print("密码已重置，旧会话已失效: {0}".format(username))
    return 0


if __name__ == "__main__":
    sys.exit(main())
