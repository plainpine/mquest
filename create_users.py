# create_users.py
# create_users.py

from models import db, User
from werkzeug.security import generate_password_hash
from app import app

# 一括作成したいユーザー情報のリスト
users_to_create = [
    {"username": "admin1", "password": "pass", "role": "admin", "nickname": "管理者１"},
    {"username": "parent01", "password": "pass", "role": "parent", "nickname": "A保護者"},
    {"username": "parent02", "password": "pass", "role": "parent", "nickname": "B保護者"},
    {"username": "student01", "password": "pass", "role": "student", "nickname": "A生徒", "parent_username": "parent01"},
    {"username": "student02", "password": "pass", "role": "student", "nickname": "B生徒兄", "parent_username": "parent02"},
    {"username": "student03", "password": "pass", "role": "student", "nickname": "B生徒弟", "parent_username": "parent02"},
]

with app.app_context():
    db.create_all()
    print("✅ テーブルを作成しました。")

    # 事前に保護者を作成しておく（studentより先に）
    username_to_user = {}

    for u in users_to_create:
        existing = User.query.filter_by(username=u["username"]).first()
        if existing:
            print(f"ユーザー {u['username']} は既に存在します。スキップします。")
            username_to_user[u["username"]] = existing
            continue

        parent_id = None
        if u["role"] == "student" and "parent_username" in u:
            parent = User.query.filter_by(username=u["parent_username"]).first()
            if parent:
                parent_id = parent.id
            else:
                print(f"⚠️ 保護者ユーザー {u['parent_username']} が存在しません。")

        user = User(
            username=u["username"],
            password_hash=generate_password_hash(u["password"]),
            role=u["role"],
            nickname=u.get("nickname"),
            parent_id=parent_id
        )

        db.session.add(user)
        print(f"✅ ユーザー {u['username']}（ロール: {u['role']}）を作成しました。")
        db.session.flush()  # IDを取得するため

        username_to_user[u["username"]] = user

    db.session.commit()
    print("✅ すべてのユーザー作成処理が完了しました。")
