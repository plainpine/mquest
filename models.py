# models.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'student', 'parent'
    is_first_login = db.Column(db.Boolean, default=True, nullable=False)
    nickname = db.Column(db.String(80), nullable=True)
    avatar = db.Column(db.LargeBinary, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # ▼ 世界制覇機能用のカラム
    user_level = db.Column(db.Integer, default=1)
    medals = db.Column(db.Integer, default=0)
    user_title = db.Column(db.String(100), default='見習い')

    # ▼ 保護者 ↔ 生徒の関係（1対多）
    children = db.relationship('User', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_student(self):
        return self.role == 'student'

    def is_parent(self):
        return self.role == 'parent'


class Quest(db.Model):
    __tablename__ = 'quests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(10), nullable=False)
    questname = db.Column(db.String(100), nullable=False)

    # ▼ 世界制覇機能用のカラム
    world_name = db.Column(db.String(100))

    # 明示的に one-to-many の関係を定義
    questions = db.relationship('Question', back_populates='quest', cascade="all, delete-orphan")




class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey('quests.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)       # 'choice', 'numeric', 'sort'
    text = db.Column(db.Text, nullable=False)
    choices = db.Column(db.Text)  # JSON文字列（list）として格納
    answer = db.Column(db.Text)   # JSON文字列（int, list, dictなど）
    explanation = db.Column(db.Text, nullable=True)

    # Quest側と対になる明示的な関係
    quest = db.relationship('Quest', back_populates='questions')


class QuestHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quest_id = db.Column(db.Integer, db.ForeignKey('quests.id'), nullable=False)
    correct = db.Column(db.Boolean, nullable=False, default=False) 
    is_cleared = db.Column(db.Boolean, default=False)
    attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'quest_id', name='unique_user_quest'),
    )

# ▼ 世界制覇機能用の進捗管理モデル
class UserProgress(db.Model):
    __tablename__ = 'user_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quest_id = db.Column(db.Integer, db.ForeignKey('quests.id'), nullable=False)
    status = db.Column(db.String(50), default='unlocked', nullable=False)  #例: 'unlocked', 'cleared'
    conquered_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'quest_id', name='unique_user_quest_progress'),
    )

    user = db.relationship('User', backref=db.backref('progress', lazy='dynamic'))
    quest = db.relationship('Quest', backref=db.backref('progress', lazy='dynamic'))
