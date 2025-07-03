from app import app
from models import Quest

with app.app_context():
    results = Quest.query.filter_by(title='計算選択問題', level='Lv1').all()
    for quest in results:
        print(quest.id, quest.title, quest.level)
    