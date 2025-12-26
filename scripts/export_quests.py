
import os
import sys
import json

# プロジェクトのルートディレクトリをシステムパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app import app, db, SUBJECT_KEY_TO_JP
from models import Quest, Question

def export_data_to_json():
    """
    データベースからクエストと質問のデータを取得し、
    'quests.json' と同じフォーマットで 'quests_exported.json' に出力します。
    """
    output_data = {}

    with app.app_context():
        # すべてのクエストを取得
        quests = Quest.query.order_by(Quest.id).all()

        for quest in quests:
            # 各クエストのデータを構築
            quest_data = {
                "questname": quest.questname,
                "level": quest.level,
                "subject": SUBJECT_KEY_TO_JP.get(quest.title, quest.title), # titleを日本語のsubjectに変換
                "world_name": quest.world_name,
                "questions": []
            }

            # 各クエストに紐づく質問を取得
            for q in quest.questions:
                question_data = {
                    "type": q.type,
                    "text": q.text,
                    "explanation": q.explanation
                }

                # 'choices' はJSON文字列として保存されていることが多い
                try:
                    choices = json.loads(q.choices) if q.choices else None
                except (json.JSONDecodeError, TypeError):
                    choices = q.choices # パースに失敗した場合はそのまま使用

                # 'answer' の扱いをタイプごとに制御
                answer = None
                if q.type in ['choice', 'multiple_choice', 'sort', 'fill_in_the_blank_en']:
                    # これらのタイプの answer は文字列なので、loads しない
                    answer = q.answer
                else:
                    # numeric, svg_interactive などはJSON文字列の可能性
                    try:
                        answer = json.loads(q.answer) if q.answer else None
                    except (json.JSONDecodeError, TypeError):
                        answer = q.answer # パースに失敗した場合はそのまま使用

                # quests.jsonのフォーマットに合わせてキーを調整
                if q.type == 'choice' or q.type == 'multiple_choice':
                    question_data['choices'] = choices
                    question_data['answer'] = answer
                elif q.type == 'numeric':
                    question_data['answers'] = answer
                elif q.type == 'sort' or q.type == 'fill_in_the_blank_en':
                    question_data['answer'] = answer
                elif q.type == 'svg_interactive':
                    question_data['svg_content'] = choices # choicesフィールドにSVGコンテンツが格納されている
                    question_data['sub_questions'] = answer # answerフィールドにサブ問題が格納されている
                else: # フォールバック
                    question_data['choices'] = choices
                    question_data['answer'] = answer

                quest_data["questions"].append(question_data)
            
            output_data[str(quest.id)] = quest_data

    # エクスポートするファイル名を指定
    output_filename = os.path.join(os.path.dirname(__file__), 'quests_exported.json')

    # データをJSONファイルに書き出し
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print(f"データが正常に '{output_filename}' へエクスポートされました。")

if __name__ == "__main__":
    export_data_to_json()
