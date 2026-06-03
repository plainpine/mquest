# models.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import foreign, remote

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
    attempt_logs = db.relationship('QuestAttemptLog', back_populates='user', cascade="all, delete-orphan")

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
    __bind_key__ = 'content'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(10), nullable=False)
    questname = db.Column(db.String(100), nullable=False)

    # ▼ 世界制覇機能用のカラム
    world_name = db.Column(db.String(100))

    # 同一DB内の関係
    questions = db.relationship('Question', back_populates='quest', cascade="all, delete-orphan", lazy='joined')
    
    # 異なるDB間（BINDS）の関係
    # Questオブジェクトから他DBのデータを参照できるように primaryjoin を設定
    progress = db.relationship('UserProgress', 
                               primaryjoin="Quest.id == foreign(remote(UserProgress.quest_id))",
                               back_populates='quest',
                               sync_backref=False,
                               cascade="all, delete-orphan")
    history = db.relationship('QuestHistory', 
                              primaryjoin="Quest.id == foreign(remote(QuestHistory.quest_id))",
                              back_populates='quest',
                              sync_backref=False,
                              cascade="all, delete-orphan")
    attempt_logs = db.relationship('QuestAttemptLog', 
                                   primaryjoin="Quest.id == foreign(remote(QuestAttemptLog.quest_id))",
                                   back_populates='quest',
                                   sync_backref=False,
                                   cascade="all, delete-orphan")




class Question(db.Model):
    __tablename__ = 'questions'
    __bind_key__ = 'content'
    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey('quests.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, nullable=False)
    choices = db.Column(db.Text)
    answer = db.Column(db.Text)
    explanation = db.Column(db.Text, nullable=True)

    quest = db.relationship('Quest', back_populates='questions')


class QuestHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quest_id = db.Column(db.Integer, nullable=False)
    correct = db.Column(db.Boolean, nullable=False, default=False) 
    is_cleared = db.Column(db.Boolean, default=False)
    cleared_count = db.Column(db.Integer, default=0)
    attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'quest_id', name='unique_user_quest'),
    )
    # 反対側からもQuestを特定できるように設定
    quest = db.relationship('Quest', 
                            primaryjoin="remote(Quest.id) == foreign(QuestHistory.quest_id)",
                            back_populates='history',
                            sync_backref=False)


# ▼ 世界制覇機能用の進捗管理モデル
class UserProgress(db.Model):
    __tablename__ = 'user_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quest_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='unlocked', nullable=False)
    conquered_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'quest_id', name='unique_user_quest_progress'),
    )

    user = db.relationship('User', backref=db.backref('progress', lazy='dynamic'))
    quest = db.relationship('Quest', 
                            primaryjoin="remote(Quest.id) == foreign(UserProgress.quest_id)",
                            back_populates='progress',
                            sync_backref=False)


class QuestAttemptLog(db.Model):
    __tablename__ = 'quest_attempt_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quest_id = db.Column(db.Integer, nullable=False)
    correct_answers = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    attempted_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='attempt_logs')
    quest = db.relationship('Quest', 
                            primaryjoin="remote(Quest.id) == foreign(QuestAttemptLog.quest_id)",
                            back_populates='attempt_logs',
                            sync_backref=False)
