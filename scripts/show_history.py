import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from models import db, QuestHistory

with app.app_context():
    results = QuestHistory.query.all()
    for r in results:
        print(f"ID: {r.id}, user_id: {r.user_id}, quest_id: {r.quest_id}, correct: {r.correct}, attempts: {r.attempts}, last_attempt: {r.last_attempt}")
