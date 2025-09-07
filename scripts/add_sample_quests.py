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

def load_quest_data():
    with open(QUEST_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

with app.app_context():
    # 登録前に既存のデータを削除
    # Question.query.delete()
    # Quest.query.delete()
    # db.session.commit()
    # print("Existing quests and questions deleted.")

    quest_data = load_quest_data()
    for qset in quest_data.values():
        # クエスト全体を登録
        quest = Quest(
            title=qset["title"],
            level=qset["level"],
            world_name=qset["title"],  # titleをデフォルト値として設定
            fantasy_name=qset["title"] # titleをデフォルト値として設定
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
    print("Sample quests and questions have been added.")
