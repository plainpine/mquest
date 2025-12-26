# scripts/add_sample_quests.py
import sys
import os
import json
import re

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# app.pyから直接appとdbをインポート
from app import app, db
from models import Quest, Question

QUEST_DATA_FILE = os.path.join(os.path.dirname(__file__), 'quests.json')
SVG_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'maps')

# 日本語の科目名と英語の識別子を対応付ける
SUBJECT_KEY_MAP = {
    "数学": "math",
    "英語": "english",
    "国語": "japanese",
    "理科": "science",
    "社会": "social"
}

# どの科目がどのSVGファイルとクエストIDのプレフィックスに対応するかを定義
SUBJECT_SVG_MAP = {
    'math': {'file': 'Europe.svg', 'prefix': 'europe'},
    'english': {'file': 'Americus.svg', 'prefix': 'americus'},
    'japanese': {'file': 'Zipangu.svg', 'prefix': 'zipangu'}
}

def load_quest_data():
    with open(QUEST_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# 1. quests.jsonから科目ごとのクエストIDリストを作成
def get_quests_by_subject():
    with app.app_context():
        quests = Quest.query.order_by(Quest.id).all()
        
        subject_quests = {
            'math': [],
            'english': [],
            'japanese': []
        }

        for quest in quests:
            if quest.title in subject_quests:
                subject_quests[quest.title].append(str(quest.id))
                
    return subject_quests

# 2. SVGファイルを読み込み、IDを置換する
def process_svg_file(filename, prefix, quest_ids):
    filepath = os.path.join(SVG_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    id_pattern = re.compile(r'<(?:path|g|rect|circle|polygon|polyline|text|tspan)[^>]*?(\s)id="([^"]+)"')
    quest_id_iter = iter(quest_ids)

    def replacer(match):
        try:
            new_id = next(quest_id_iter)
            print(f"  - Replacing id='{match.group(2)}' with id='{new_id}' in {filename}")
            return f'{match.group(0).split(' id=')[0]} id="{new_id}"'
        except StopIteration:
            print(f"  - No more quest IDs. Keeping original id='{match.group(2)}'")
            return match.group(0)

    modified_content = id_pattern.sub(replacer, content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    print(f"Finished processing {filename}.\n")


if __name__ == '__main__':
    with app.app_context():
        # 登録前に既存のデータを削除
        print("Deleting existing quests and questions...")
        Question.query.delete()
        Quest.query.delete()
        db.session.commit()
        print("Existing quests and questions deleted.")

        quest_data = load_quest_data()
        print("Adding new quests and questions...")
        for quest_id_str, qset in quest_data.items():
            subject_jp = qset.get("subject", "その他")
            subject_key = SUBJECT_KEY_MAP.get(subject_jp, "misc")
            
            quest_id = int(quest_id_str)

            quest = Quest(
                id=quest_id,
                title=subject_key,
                level=qset["level"],
                questname=qset["questname"],
                world_name=qset.get("world_name", "fantasy")
            )
            db.session.add(quest)
            db.session.flush()

            for q in qset["questions"]:
                # choicesの処理
                choices_data = None
                if q.get("type") == "choice" or q.get("type") == "multiple_choice":
                    choices_data = json.dumps(q.get("choices")) # JSONリストを文字列化
                elif q.get("type") == "svg_interactive":
                    choices_data = q.get("svg_content") # SVGコンテンツをそのまま

                # answerの処理
                answer_data = None
                if q.get("type") == "numeric":
                    answer_data = json.dumps(q.get("answers")) # 数値問題の答えはJSONリスト
                elif q.get("type") == "svg_interactive":
                    answer_data = json.dumps(q.get("sub_questions")) # SVG問題のサブ質問はJSONリスト
                elif q.get("type") == "choice" or q.get("type") == "multiple_choice":
                    answer_data = q.get("answer") # choiceとmultiple_choiceの答えはそのまま文字列

                question = Question(
                    quest_id=quest.id,
                    type=q["type"],
                    text=q["text"],
                    explanation=q.get("explanation"),
                    choices=choices_data,
                    answer=answer_data
                )
                db.session.add(question)

        db.session.commit()
        print("Sample quests and questions have been added successfully.")

    # # SVG IDの更新処理 (現在、この部分は新しい構造に対応していません)
    # print("\nStarting SVG ID update process...\n")
    # subject_quests = get_quests_by_subject()
    
    # print("Quest IDs grouped by subject:")
    # print(json.dumps(subject_quests, indent=2))
    # print("\n")

    # for subject, data in SUBJECT_SVG_MAP.items():
    #     if subject in subject_quests and subject_quests[subject]:
    #         print(f"Processing {data['file']} for subject '{subject}'...")
    #         process_svg_file(data['file'], data['prefix'], subject_quests[subject])
    #     else:
    #         print(f"No quests found for subject '{subject}', skipping {data['file']}.\n")
    
    # print("SVG ID update process finished.")
