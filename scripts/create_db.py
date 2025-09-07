# scripts/create_db.py
import os
import sys

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# app.pyから直接appとdbをインポート
from app import app, db

with app.app_context():
    print("Dropping all database tables...")
    db.drop_all()
    print("Creating all database tables...")
    db.create_all()
    print("Tables have been created successfully.")
