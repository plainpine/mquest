# create_users.py
from models import db, User
from werkzeug.security import generate_password_hash
from app import app

# 一括作成したいユーザー情報のリスト
users_to_create = [
    {"username": "admin1", "password": "pass", "role": "admin"},
    {"username": "student01", "password": "pass", "role": "student"},
    {"username": "student02", "password": "pass", "role": "student"},
    {"username": "parent01", "password": "pass", "role": "parent"},
    {"username": "parent02", "password": "pass", "role": "parent"},
]

with app.app_context():
    db.create_all()
    print("✅ テーブルを作成しました。")

    for u in users_to_create:
        existing = User.query.filter_by(username=u["username"]).first()
        if existing:
            print(f"ユーザー {u['username']} は既に存在します。スキップします。")
            continue

        user = User(
            username=u["username"],
            password_hash=generate_password_hash(u["password"]),
            role=u["role"]
        )
        db.session.add(user)
        print(f"ユーザー {u['username']}（ロール: {u['role']}）を作成しました。")

    db.session.commit()
    print("✅ すべてのユーザー作成処理が完了しました。")