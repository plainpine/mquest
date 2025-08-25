import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from flask import Flask
from models import db, Quest, Question    # Questモデルは質問単位でデータを持つ想定

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mquest.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

QUEST_DATA_FILE = os.path.join(os.path.dirname(__file__), 'quests.json')

def load_quest_data():
    with open(QUEST_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

with app.app_context():
    # ✅ 登録前に既存のデータを削除
    Question.query.delete()
    Quest.query.delete()
    db.session.commit()

    quest_data = load_quest_data()
    for qset in quest_data.values():
        # クエスト全体を登録
        quest = Quest(
            title=qset["title"],
            level=qset["level"]
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
    print("✅ クエストと問題データを登録しました。")

from app import app
from models import Quest

with app.app_context():
    quests = Quest.query.all()
    for q in quests:
        print(f"id={q.id}, title={q.title}, level={q.level}")
