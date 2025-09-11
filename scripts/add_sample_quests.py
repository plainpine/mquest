# scripts/add_sample_quests.py
import sys
import os
import json

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# app.pyから直接appとdbをインポート
from app import app, db
from models import Quest, Question

QUEST_DATA_FILE = os.path.join(os.path.dirname(__file__), 'quests.json')

# JSON内のタイトルと、英語識別子・日本語名・マップ名を対応付ける
QUEST_MAP = {
    "計算選択問題": {"subject_key": "math", "subject_jp": "数学", "world": "europe"},
    "英語文法":    {"subject_key": "english", "subject_jp": "英語", "world": "americus"},
    "英文並べ替え":  {"subject_key": "english", "subject_jp": "英語", "world": "americus"},
    "計算問題":    {"subject_key": "math", "subject_jp": "数学", "world": "europe"}
}

def load_quest_data():
    with open(QUEST_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

with app.app_context():
    # 登録前に既存のデータを削除
    print("Deleting existing quests and questions...")
    Question.query.delete()
    Quest.query.delete()
    db.session.commit()
    print("Existing quests and questions deleted.")

    quest_data = load_quest_data()
    print("Adding new quests and questions with ASCII identifiers...")
    for qset in quest_data.values():
        specific_title = qset["title"]
        mapping = QUEST_MAP.get(specific_title)

        if not mapping:
            print(f"  - WARNING: No mapping found for title '{specific_title}'. Skipping.")
            continue

        # クエスト全体を登録
        quest = Quest(
            title=mapping["subject_key"], # 例: "math"
            level=qset["level"],
            world_name=mapping["world"],   # 例: "europe"
            fantasy_name=specific_title    # 例: "計算選択問題"
        )
        db.session.add(quest)
        db.session.flush()  # quest.id を取得するために一旦flush

        for q in qset["questions"]:
            question = Question(
                quest_id=quest.id,
                type=q["type"],
                text=q["text"],
                choices=json.dumps(q.get("choices")) if "choices" in q else None,
                answer=json.dumps(q.get("answer") if q["type"] != "numeric" else q["answers"])
            )
            db.session.add(question)

    db.session.commit()
    print("Sample quests and questions have been added successfully.")