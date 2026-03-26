import sys
import os

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app import app
from models import Quest

with app.app_context():
    results = Quest.query.filter_by(title='計算選択問題', level='Lv1').all()
    for quest in results:
        print(quest.id, quest.title, quest.level)
    