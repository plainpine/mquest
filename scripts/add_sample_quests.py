import json
from flask import Flask
from models import db, Quest, Question    # Questモデルは質問単位でデータを持つ想定

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mquest.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

QUEST_DATA = {
    1: {
        "title": "計算選択問題",
        "level": "Lv1",
        "questions": [
            {
                "type": "choice",
                "text": "$-8 + 5 = ?$",
                "choices": ["$-13$", "$3$", "$-3$", "$13$"],
                "answer": 2
            },
            {
                "type": "choice",
                "text": "$(6 + 4) \\div 2 = ?$",
                "choices": ["$5$", "$2$", "$20$", "$8$"],
                "answer": 0
            },
            {
                "type": "choice",
                "text": "$\\frac{2}{3} + \\frac{1}{6} = ?$",
                "choices": ["$\\frac{3}{6}$", "$\\frac{4}{9}$", "$\\frac{5}{6}$", "$\\frac{1}{2}$"],
                "answer": 2
            },
            {
                "type": "choice",
                "text": "$-2 \\times (-6) = ?$",
                "choices": ["$-12$", "$12$", "$-4$", "$4$"],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "$7 - (-5) = ?$",
                "choices": ["$2$", "$12$", "$-2$", "$7$"],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "$\\frac{5}{8} - \\frac{1}{4} = ?$",
                "choices": ["$\\frac{3}{8}$", "$\\frac{4}{8}$", "$\\frac{1}{2}$", "$\\frac{5}{4}$"],
                "answer": 0
            },
            {
                "type": "choice",
                "text": "$(-4) \\div 2 = ?$",
                "choices": ["$2$", "$-2$", "$-6$", "$8$"],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "$3 \\times (-5) + 2 = ?$",
                "choices": ["$-15$", "$-17$", "$-13$", "$13$"],
                "answer": 2
            },
            {
                "type": "choice",
                "text": "$(-10) + (-3) = ?$",
                "choices": ["$13$", "$-7$", "$-13$", "$7$"],
                "answer": 2
            },
            {
                "type": "choice",
                "text": "$(4 + 6) \\times (-2) = ?$",
                "choices": ["$-20$", "$-12$", "$20$", "$12$"],
                "answer": 0
            }
        ]
    },
    2: {
        "title": "英語文法",
        "level": "Lv1",
        "questions": [
            {
                "type": "choice",
                "text": "次のうち正しい英文はどれ？",
                "choices": ["He go to school.", "He goes to school.", "He going school.", "He go school."],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "主語はどれ？「I like apples.」",
                "choices": ["I", "like", "apples", "."],
                "answer": 0
            }
        ]
    },
    3: {
        "title": "英文並べ替え",
        "level": "Lv1",
        "questions": [
            {
                "type": "sort",
                "text": "am / I / not / boy / a / .",
                "answer": "I am not a boy ."
            }
        ]
    },
    4: {
        "title": "計算問題",
        "level": "Lv1",
        "questions": [
            {
                "type": "numeric",
                "text": "以下の方程式を解け<br>x + y = 10<br>2x + y = 12",
                "answers": [
                    {"label": "x", "answer": 2},
                    {"label": "y", "answer": 8}
                ]
            }
        ]
    },
    5: {
        "title": "計算選択問題",
        "level": "Lv1",
        "questions": [
            {
                "type": "choice",
                "text": "2 + 2 = ?",
                "choices": ["3", "4", "5", "6"],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "3 * 3 = ?",
                "choices": ["6", "7", "8", "9"],
                "answer": 3
            },
            {
                "type": "choice",
                "text": "**次の式を解いてください：**\n\n$x^2 + 2x + 1 = 0$",
                "choices": ["$x = -1$", "$x = 0$", "$x = 1$", "$x = 2$"],
                "answer": 0
            },
            {
                "type": "choice",
                "text": "**次の式を展開してください：**\n\n$(x + y)^2$",
                "choices": ["$x^2 + y^2$", "$x^2 + 2xy + y^2$", "$x^2 + xy + y^2$", "$x + y$"],
                "answer": 1
            }
        ]
    },
    6: {
        "title": "計算選択問題",
        "level": "Lv1",
        "questions": [
            {
                "type": "choice",
                "text": "2 + 2 = ?",
                "choices": ["3", "4", "5", "6"],
                "answer": 1
            },
            {
                "type": "choice",
                "text": "3 * 3 = ?",
                "choices": ["6", "7", "8", "9"],
                "answer": 3
            },
            {
                "type": "choice",
                "text": "**次の式を解いてください：**\n\n$x^2 + 2x + 1 = 0$",
                "choices": ["$x = -1$", "$x = 0$", "$x = 1$", "$x = 2$"],
                "answer": 0
            },
            {
                "type": "choice",
                "text": "**次の式を展開してください：**\n\n$(x + y)^2$",
                "choices": ["$x^2 + y^2$", "$x^2 + 2xy + y^2$", "$x^2 + xy + y^2$", "$x + y$"],
                "answer": 1
            }
        ]
    },

}

with app.app_context():
    # ✅ 登録前に既存のデータを削除
    Question.query.delete()
    Quest.query.delete()
    db.session.commit()

    for qset in QUEST_DATA.values():
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
