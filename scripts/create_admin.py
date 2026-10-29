#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create the first platform administrator.

Never uses a hardcoded password.  Interactive by default; CI/trusted
environment can provide ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_EMAIL /
ADMIN_NICKNAME.  Passwords are never printed or written to logs.
"""
from __future__ import absolute_import

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.auth_service import AuthError, AuthService
from backend.database import get_database


def _read_credentials():
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    nickname = os.environ.get("ADMIN_NICKNAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not username:
        username = input("管理员用户名: ").strip()
    if not nickname:
        nickname = input("管理员昵称（回车使用用户名）: ").strip() or username
    if not email:
        email = input("管理员邮箱（可选，回车跳过）: ").strip()
    if not password:
        password = getpass.getpass("管理员密码: ")
        confirm = getpass.getpass("再次输入密码: ")
        if password != confirm:
            raise SystemExit("两次输入的密码不一致")
    return username, nickname, email, password


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the first AIGV Studio platform administrator.")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--add", action="store_true", help="allow creating an additional admin")
    parser.add_argument("--promote-existing", metavar="USERNAME", help="explicitly promote an existing ordinary user")
    args = parser.parse_args(argv)

    os.environ.setdefault("DATA_DIR", args.data_dir)
    get_database(os.path.join(args.data_dir, "aigv.db"))
    service = AuthService(args.data_dir)

    if args.promote_existing:
        row = service.get_user_by_username(args.promote_existing)
        if not row:
            print("用户不存在: {0}".format(args.promote_existing), file=sys.stderr)
            return 2
        if row.get("role") == "admin" and row.get("status") == "active":
            print("该用户已经是管理员，无需重复操作。", file=sys.stderr)
            return 3
        if row.get("status") != "active":
            print("该账户当前不是 active 状态，请先在管理后台启用后再提升。", file=sys.stderr)
            return 2
        answer = input(
            "确认将普通用户 {0} 提升为平台管理员？输入 yes 继续: ".format(args.promote_existing)
        ).strip().lower()
        if answer != "yes":
            print("已取消。")
            return 0
        try:
            service.admin_update_role(row["id"], "admin", actor_id="cli:create_admin")
        except AuthError as exc:
            print("提升失败: {0}".format(exc.message), file=sys.stderr)
            return 2
        try:
            from backend.audit_service import get_audit_service
            get_audit_service(args.data_dir).record_audit(
                user_id=None,
                tenant_id=row.get("tenant_id"),
                project_id=None,
                action="admin_role_change",
                target_type="user",
                target_id=row["id"],
                result="success",
                metadata={
                    "actor": "cli:create_admin",
                    "before": row.get("role"),
                    "after": "admin",
                },
            )
        except Exception as exc:
            print("警告：审计写入失败: {0}".format(str(exc)), file=sys.stderr)
        print("已提升为平台管理员: {0}".format(args.promote_existing))
        return 0

    active_admins = service.count_active_admins()
    if active_admins and not args.add:
        print(
            "已存在 {0} 个有效管理员。为避免重复创建，默认停止；如确需新增请加 --add。".format(active_admins),
            file=sys.stderr,
        )
        return 3

    username, nickname, email, password = _read_credentials()
    try:
        user = service.create_user(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            role="admin",
        )
    except AuthError as exc:
        print("创建失败: {0}".format(exc.message), file=sys.stderr)
        return 2

    print("管理员已创建: {0} (id={1})".format(user["username"], user["id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
