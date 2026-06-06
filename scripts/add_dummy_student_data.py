
import os
import json
from datetime import datetime, timezone, timedelta
import random
from app import app, db, User, Quest, UserProgress, QuestHistory, QuestAttemptLog

def add_dummy_student_data():
    with app.app_context():
        # 1. Create Parent "guestp"
        parent = User.query.filter_by(username='guestp').first()
        if not parent:
            parent = User(username='guestp', role='parent', nickname='ゲスト保護者')
            parent.set_password('password123')
            db.session.add(parent)
            db.session.flush()
            print("Created parent: guestp")
        else:
            print("Parent guestp already exists")

        # 2. Create Student "guests"
        student = User.query.filter_by(username='guests').first()
        if not student:
            student = User(
                username='guests', 
                role='student', 
                nickname='ゲスト生徒',
                parent_id=parent.id,
                target_levels_json=json.dumps({"math": "Lv4", "english": "Lv1", "japanese": "Lv1"})
            )
            student.set_password('password123')
            student.is_first_login = False
            db.session.add(student)
            db.session.flush()
            print("Created student: guests")
        else:
            print("Student guests already exists")
            student.parent_id = parent.id
            student.target_levels_json = json.dumps({"math": "Lv4", "english": "Lv1", "japanese": "Lv1"})

        # 3. Add Dummy Progress
        # We'll clear about 50-70% of quests in the target levels
        subjects = [
            ('math', 'Lv4', 15),
            ('english', 'Lv1', 12),
            ('japanese', 'Lv1', 18)
        ]

        now = datetime.now(timezone.utc)
        
        # Clear existing dummy data for this student to avoid duplicates if re-run
        UserProgress.query.filter_by(user_id=student.id).delete()
        QuestHistory.query.filter_by(user_id=student.id).delete()
        QuestAttemptLog.query.filter_by(user_id=student.id).delete()

        for title, level, count in subjects:
            quests = Quest.query.filter_by(title=title, level=level).limit(count).all()
            print(f"Adding progress for {title} {level}: {len(quests)} quests")
            
            for i, quest in enumerate(quests):
                # Random number of attempts (1 to 5)
                attempts = random.randint(1, 5)
                
                # History
                history = QuestHistory(
                    user_id=student.id,
                    quest_id=quest.id,
                    correct=True,
                    is_cleared=True,
                    cleared_count=1,
                    attempts=attempts,
                    last_attempt=now - timedelta(days=random.randint(0, 85))
                )
                db.session.add(history)

                # Progress
                progress = UserProgress(
                    user_id=student.id,
                    quest_id=quest.id,
                    status='cleared',
                    conquered_at=history.last_attempt
                )
                db.session.add(progress)

                # Logs (multiple logs if multiple attempts)
                for a in range(attempts):
                    # Only the last one is correct
                    is_correct = (a == attempts - 1)
                    q_count = len(quest.questions) if quest.questions else 5
                    correct_answers = q_count if is_correct else random.randint(0, q_count - 1)
                    
                    log = QuestAttemptLog(
                        user_id=student.id,
                        quest_id=quest.id,
                        correct_answers=correct_answers,
                        total_questions=q_count,
                        attempted_at=history.last_attempt - timedelta(hours=random.randint(0, 24))
                    )
                    db.session.add(log)

        db.session.commit()
        print("Successfully added dummy data for guests!")

if __name__ == '__main__':
    add_dummy_student_data()
