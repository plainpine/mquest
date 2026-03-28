
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_renumber.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Quest(db.Model):
    __tablename__ = 'quests'
    id = db.Column(db.Integer, primary_key=True)
    questname = db.Column(db.String(100), nullable=False)
    questions = db.relationship('Question', backref='quest')

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey('quests.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()
    
    # Create sample data
    q1 = Quest(id=1, questname='Quest 1')
    db.session.add(q1)
    db.session.commit()
    
    qn1 = Question(id=500, quest_id=1, text='Q1')
    qn2 = Question(id=300, quest_id=1, text='Q2')
    db.session.add_all([qn1, qn2])
    db.session.commit()
    
    print(f"Before: IDs={[q.id for q in sorted(Question.query.all(), key=lambda x: x.id)]}")
    
    # Renumbering logic
    questions = sorted(Question.query.filter_by(quest_id=1).all(), key=lambda x: x.id)
    for i, q in enumerate(questions):
        new_id = 101 + i
        old_id = q.id
        if old_id != new_id:
            db.session.execute(text("UPDATE questions SET id = :new_id WHERE id = :old_id"),
                               {'new_id': new_id, 'old_id': old_id})
    db.session.commit()
    
    print(f"After: IDs={[q.id for q in sorted(Question.query.all(), key=lambda x: x.id)]}")

    db.drop_all()
os.remove('test_renumber.db')
