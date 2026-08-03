from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_file, Response, get_flashed_messages, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case
from sqlalchemy.exc import IntegrityError, OperationalError
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from models import QuestHistory, Quest, Question, QuestAttemptLog
import os
import json
import re
import logging
import random
import time
import atexit
import csv
from utils.svg_preview_bp import bp as svg_preview_bp # Import the blueprint
from copy import deepcopy
# ... (rest of imports/mappings)

def cleanup_database():
    """
    アプリケーション終了時にSQLiteのWALファイルをクリア（統合）する処理。
    すべてのBind（user_db, content_dbなど）に対して実行する。
    """
    with app.app_context():
        try:
            # すべてのエンジン（デフォルト + binds）に対してチェックポイントを実行
            for engine in db.engines.values():
                with engine.connect() as conn:
                    conn.execute(db.text("PRAGMA wal_checkpoint(TRUNCATE);"))
            
            # 接続を閉じる
            db.session.remove()
            print("\nAll database checkpoints completed and connections closed.")
        except Exception as e:
            print(f"\nError during database cleanup: {e}")

# アプリ終了時に実行されるように登録
atexit.register(cleanup_database)

# 科目キーと日本語名のマッピング
SUBJECT_KEY_TO_JP = {
    'math': '数学',
    'english': '英語',
    'japanese': '国語',
    'misc': 'その他'
}
# 日本語名から英語キーへの逆引きマップ
SUBJECT_JP_TO_KEY = {v: k for k, v in SUBJECT_KEY_TO_JP.items()}

from models import db, User, Quest, UserProgress, HabatanBookmark, HabatanStudyStats, HabatanDailyHistory

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=os.path.join(basedir, 'templates'))
app.secret_key = 'your-secret-key'  # セッション管理に必要

@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None

@app.context_processor
def inject_markdown_help():
    def get_markdown_help():
        try:
            filepath = os.path.join(basedir, 'Markdown_help.md')
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            app.logger.error(f"Error reading Markdown_help.md: {e}")
            return "ヘルプファイルを読み込めませんでした。"
    return dict(get_markdown_help=get_markdown_help)


# データベース設定（例: SQLite）
# Flask-SQLAlchemyはデフォルトでinstanceフォルダを探すため、パスから 'instance/' を除外するか絶対パスを使用します。
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'mquest_user.db')
app.config['SQLALCHEMY_BINDS'] = {
    'content': 'sqlite:///' + os.path.join(basedir, 'instance', 'mquest_content.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DBとLoginManagerの初期化
db.init_app(app)

from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.register_blueprint(svg_preview_bp) # Register the blueprint

def safe_commit(retries=5, delay=1.0):
    """
    Attempts to commit the current session, with retries for OperationalError (e.g., disk I/O error).
    """
    for i in range(retries):
        try:
            db.session.commit()
            return True
        except OperationalError as e:
            if "disk I/O error" in str(e) or "database is locked" in str(e):
                app.logger.warning(f"Database commit failed (attempt {i+1}/{retries}): {e}. Retrying in {delay}s...")
                db.session.rollback()
                time.sleep(delay)
                continue
            else:
                db.session.rollback()
                raise
        except Exception:
            db.session.rollback()
            raise
    # Final attempt
    return db.session.commit()

def safe_get(model, ident, retries=5, delay=1.0):
    """
    Attempts to get a record by ID with retries for OperationalError.
    """
    for i in range(retries):
        try:
            return db.session.get(model, ident)
        except OperationalError as e:
            if "disk I/O error" in str(e) or "database is locked" in str(e):
                app.logger.warning(f"Database get failed (attempt {i+1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise
    return db.session.get(model, ident)

def safe_query_all(query, retries=5, delay=1.0):
    """
    Attempts to execute a query (all()) with retries for OperationalError.
    """
    for i in range(retries):
        try:
            return query.all()
        except OperationalError as e:
            if "disk I/O error" in str(e) or "database is locked" in str(e):
                app.logger.warning(f"Database query all failed (attempt {i+1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise
    return query.all()

def safe_query_first(query, retries=5, delay=1.0):
    """
    Attempts to execute a query (first()) with retries for OperationalError.
    """
    for i in range(retries):
        try:
            return query.first()
        except OperationalError as e:
            if "disk I/O error" in str(e) or "database is locked" in str(e):
                app.logger.warning(f"Database query first failed (attempt {i+1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise
    return query.first()

@app.route('/')
def home():
    return redirect(url_for('login'))

# ユーザーロード用コールバック
@login_manager.user_loader
def load_user(user_id):
    return safe_get(User, int(user_id))

# ユーザーログイン処理
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = safe_query_first(User.query.filter_by(username=username))

        if user and user.check_password(password):
            login_user(user)
            session['username'] = user.username # セッションにユーザー名をセット
            session['nickname'] = user.nickname # セッションにニックネームをセット
            if user.is_first_login:
                return redirect(url_for('change_password'))  # 初回ログイン時にパスワード変更ページへ
            # セッションにroleとuser_idをセット
            session['role'] = user.role
            session['user_id'] = user.id
            return redirect(url_for(f"dashboard_{user.role}"))
        # 失敗時はテンプレートを再表示＋エラー文
        return render_template('login.html', error="ユーザーIDまたはパスワードが間違っています。")

    return render_template('login.html')

# パスワード変更処理
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # パスワードの一致確認
        if not new_password or not confirm_password:
            return render_template('change_password.html', error="パスワードは空白にできません")
        
        if new_password != confirm_password:
            return render_template('change_password.html', error="パスワードが一致しません")

        # パスワードを更新
        current_user.set_password(new_password)
        current_user.is_first_login = False  # 初回ログインフラグを更新
        safe_commit()
        
        return redirect(url_for(f"dashboard_{current_user.role}"))

    return render_template('change_password.html')  # パスワード変更フォームを表示


# ログアウト処理
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

import io
import base64
import time
from werkzeug.utils import secure_filename

# ... (rest of imports)

# プロフィール設定処理
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    avatars_dir = os.path.join(app.static_folder, 'images', 'avatars')
    try:
        all_files = os.listdir(avatars_dir)
        # プリセットアバター（custom_で始まらないもの）と、自分のカスタムアバターのみを表示
        avatars = [f for f in all_files if (f.endswith('.svg') or f.endswith('.png') or f.endswith('.jpg')) 
                   and (not f.startswith('custom_') or f.startswith(f'custom_{current_user.id}_'))]
        
        # default.svgを先頭にする
        if 'default.svg' in avatars:
            avatars.remove('default.svg')
            avatars.insert(0, 'default.svg')
    except OSError:
        avatars = ['default.svg']

    # レベルのソート用キー関数 (例: 'Lv2' -> 2)
    def parse_level(level_str):
        if level_str.startswith('Lv'):
            try:
                return int(level_str[2:])
            except ValueError:
                pass
        return level_str

    # 利用可能な全レベルを取得
    all_levels_raw = safe_query_all(db.session.query(Quest.level).distinct())
    all_levels = sorted(list(set([l[0] for l in all_levels_raw])), key=parse_level)

    # 各科目（数学、英語、国語）に存在しているレベルを取得
    math_levels_set = set(l[0] for l in safe_query_all(db.session.query(Quest.level).filter_by(title='math').distinct()))
    target_math = current_user.target_levels.get('math')
    if target_math:
        math_levels_set.add(target_math)
    math_levels = sorted(list(math_levels_set), key=parse_level)

    english_levels_set = set(l[0] for l in safe_query_all(db.session.query(Quest.level).filter_by(title='english').distinct()))
    target_english = current_user.target_levels.get('english')
    if target_english:
        english_levels_set.add(target_english)
    english_levels = sorted(list(english_levels_set), key=parse_level)

    japanese_levels_set = set(l[0] for l in safe_query_all(db.session.query(Quest.level).filter_by(title='japanese').distinct()))
    target_japanese = current_user.target_levels.get('japanese')
    if target_japanese:
        japanese_levels_set.add(target_japanese)
    japanese_levels = sorted(list(japanese_levels_set), key=parse_level)


    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()

        avatar_choice = request.form.get('avatar', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # 目標レベルの更新
        target_math = request.form.get('target_level_math')
        target_english = request.form.get('target_level_english')
        target_japanese = request.form.get('target_level_japanese')
        current_user.target_levels_json = json.dumps({
            "math": target_math,
            "english": target_english,
            "japanese": target_japanese
        })

        # ファイルアップロードの処理
        avatar_file = request.files.get('avatar_file')
        new_avatar_filename = None

        if avatar_file and avatar_file.filename != '':
            ext = os.path.splitext(avatar_file.filename)[1].lower()
            if ext in ['.png', '.bmp']:
                # 画像をSVGに変換（埋め込み）
                try:
                    img_data = avatar_file.read()
                    base64_data = base64.b64encode(img_data).decode('utf-8')
                    mime_type = "image/png" if ext == '.png' else "image/bmp"
                    
                    # 100x100のSVGとして保存（40px円形にクリップ）
                    svg_content = f'''<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="circleView">
      <circle cx="50" cy="50" r="50" />
    </clipPath>
  </defs>
  <image width="100" height="100" href="data:{mime_type};base64,{base64_data}" clip-path="url(#circleView)" />
</svg>'''
                    
                    # 古いカスタムアバターがあれば削除
                    if current_user.avatar and current_user.avatar.startswith(f'custom_{current_user.id}_'):
                        old_path = os.path.join(avatars_dir, current_user.avatar)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    # 新しいファイル名作成
                    new_avatar_filename = f"custom_{current_user.id}_{int(time.time())}.svg"
                    with open(os.path.join(avatars_dir, new_avatar_filename), 'w', encoding='utf-8') as f:
                        f.write(svg_content)
                    
                    current_user.avatar = new_avatar_filename
                except Exception as e:
                    app.logger.error(f"Avatar upload/conversion error: {e}")
                    flash('画像のアップロードに失敗しました。', 'error')
            else:
                flash('PNGまたはBMP形式の画像を選択してください。', 'error')
        elif avatar_choice:
            # プリセット選択時、もし今の自分のアバターがカスタムなら削除する
            if current_user.avatar and current_user.avatar.startswith(f'custom_{current_user.id}_') and avatar_choice != current_user.avatar:
                old_path = os.path.join(avatars_dir, current_user.avatar)
                if os.path.exists(old_path):
                    os.remove(old_path)
            current_user.avatar = avatar_choice

        # ニックネーム更新
        current_user.nickname = nickname if nickname else None
        session['nickname'] = current_user.nickname

        # パスワード更新（入力がある場合のみ）
        if new_password:
            if new_password != confirm_password:
                flash('新しいパスワードが一致しません。', 'error')
                return render_template('profile.html', avatars=avatars, all_levels=all_levels, 
                                       math_levels=math_levels, english_levels=english_levels, japanese_levels=japanese_levels)
            
            current_user.set_password(new_password)
            current_user.is_first_login = False
            flash('パスワードを更新しました。', 'success')

        try:
            safe_commit()
            flash('プロフィールを更新しました。', 'success')
        except Exception as e:
            app.logger.error(f"Profile update error: {e}")
            flash('プロフィールの更新に失敗しました。', 'error')
            return render_template('profile.html', avatars=avatars, all_levels=all_levels, 
                                   math_levels=math_levels, english_levels=english_levels, japanese_levels=japanese_levels)

        return redirect(url_for('profile'))

    return render_template('profile.html', avatars=avatars, all_levels=all_levels, 
                           math_levels=math_levels, english_levels=english_levels, japanese_levels=japanese_levels)

HABATAN_DATA_FILE = os.path.join(basedir, 'data', 'words.json')
HABATAN_STATE_STORE = {}

def get_habatan_user_key(user=None):
    user = user or current_user
    if user and getattr(user, 'is_authenticated', False) and getattr(user, 'id', None):
        return f"user:{user.id}"
    return get_habatan_session_id()

def load_habatan_words():
    if os.path.exists(HABATAN_DATA_FILE):
        with open(HABATAN_DATA_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    return []

def get_habatan_session_id():
    return request.headers.get('X-Session-Id') or request.args.get('session_id') or request.cookies.get('session_id') or 'default'

def get_habatan_state(session_id=None):
    user_key = get_habatan_user_key()
    file_words = load_habatan_words()
    state = HABATAN_STATE_STORE.get(user_key)
    default_state = {
        'words': file_words,
        'stats': {'total': 0, 'correct': 0},
        'bookmarks': [],
        'studyDirection': 'en-ja',
        'dailyHistory': {},
        'wordOrder': 'number',
    }

    if current_user.is_authenticated and getattr(current_user, 'id', None):
        user_id = current_user.id
        stats_row = HabatanStudyStats.query.filter_by(user_id=user_id).first()
        bookmarks = [row.number for row in HabatanBookmark.query.filter_by(user_id=user_id).order_by(HabatanBookmark.number).all()]
        history_rows = HabatanDailyHistory.query.filter_by(user_id=user_id).all()
        daily_history = {row.date_key: {'studied': row.studied, 'answered': row.answered, 'correct': row.correct} for row in history_rows}
        default_state['stats'] = {'total': stats_row.total if stats_row else 0, 'correct': stats_row.correct if stats_row else 0}
        default_state['bookmarks'] = bookmarks
        default_state['dailyHistory'] = daily_history

    if state is None:
        HABATAN_STATE_STORE[user_key] = deepcopy(default_state)
        return deepcopy(default_state)

    merged_state = deepcopy(default_state)
    if current_user.is_authenticated and getattr(current_user, 'id', None):
        merged_state['studyDirection'] = state.get('studyDirection', default_state['studyDirection'])
        merged_state['wordOrder'] = state.get('wordOrder', default_state['wordOrder'])
    else:
        merged_state['stats'] = state.get('stats', default_state['stats'])
        merged_state['bookmarks'] = state.get('bookmarks', default_state['bookmarks'])
        merged_state['studyDirection'] = state.get('studyDirection', default_state['studyDirection'])
        merged_state['dailyHistory'] = state.get('dailyHistory', default_state['dailyHistory'])
        merged_state['wordOrder'] = state.get('wordOrder', default_state['wordOrder'])
    HABATAN_STATE_STORE[user_key] = deepcopy(merged_state)
    return deepcopy(merged_state)

def save_habatan_state(payload, session_id=None):
    user_key = get_habatan_user_key()
    current_state = get_habatan_state()
    if current_user.is_authenticated and getattr(current_user, 'id', None):
        user_id = current_user.id
        stats_payload = payload.get('stats', current_state.get('stats', {'total': 0, 'correct': 0}))
        bookmarks_payload = payload.get('bookmarks', current_state.get('bookmarks', []))
        daily_history_payload = payload.get('dailyHistory', current_state.get('dailyHistory', {}))

        stats_row = HabatanStudyStats.query.filter_by(user_id=user_id).first()
        if stats_row is None:
            stats_row = HabatanStudyStats(user_id=user_id)
            db.session.add(stats_row)
        stats_row.total = int(stats_payload.get('total', 0))
        stats_row.correct = int(stats_payload.get('correct', 0))
        stats_row.updated_at = datetime.now(timezone.utc)

        HabatanBookmark.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        seen_bookmarks = set()
        for number in bookmarks_payload:
            try:
                num = int(number)
            except (TypeError, ValueError):
                continue
            if num in seen_bookmarks:
                continue
            seen_bookmarks.add(num)
            db.session.add(HabatanBookmark(user_id=user_id, number=num))

        with db.session.no_autoflush:
            for date_key, values in daily_history_payload.items():
                existing = HabatanDailyHistory.query.filter_by(user_id=user_id, date_key=date_key).first()
                if existing:
                    existing.studied = int(values.get('studied', 0))
                    existing.answered = int(values.get('answered', 0))
                    existing.correct = int(values.get('correct', 0))
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    db.session.add(HabatanDailyHistory(
                        user_id=user_id,
                        date_key=date_key,
                        studied=int(values.get('studied', 0)),
                        answered=int(values.get('answered', 0)),
                        correct=int(values.get('correct', 0)),
                    ))

        safe_commit()

    current_state.update({
        'stats': payload.get('stats', current_state.get('stats', {'total': 0, 'correct': 0})),
        'bookmarks': payload.get('bookmarks', current_state.get('bookmarks', [])),
        'studyDirection': payload.get('studyDirection', current_state.get('studyDirection', 'en-ja')),
        'dailyHistory': payload.get('dailyHistory', current_state.get('dailyHistory', {})),
        'wordOrder': payload.get('wordOrder', current_state.get('wordOrder', 'number')),
        'words': load_habatan_words(),
    })
    HABATAN_STATE_STORE[user_key] = deepcopy(current_state)
    return deepcopy(current_state)

@app.route('/habatan')
@app.route('/habatan/')
@login_required
def habatan_index():
    return render_template('habatan.html')

@app.route('/habatan/study')
@login_required
def habatan_study():
    return render_template('habatan.html')

@app.route('/habatan/static/<path:filename>')
def habatan_static(filename):
    return send_from_directory(os.path.join(basedir, 'static'), filename)

@app.route('/habatan/api/state', methods=['GET', 'POST'])
@login_required
def habatan_state_api():
    session_id = get_habatan_session_id()
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        save_habatan_state(payload, session_id)
    return jsonify(get_habatan_state(session_id))

# 初回のユーザー作成（ロール付き）
@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        if role not in ['admin', 'student', 'parent', 'teacher']:
            return '無効なロールです'

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        safe_commit()
        return f"{role}ユーザー {username} を作成しました"

    return '''
        <form method="post">
            ユーザー名: <input name="username"><br>
            パスワード: <input name="password" type="password"><br>
            ロール:
            <select name="role">
                <option value="admin">管理者</option>
                <option value="student">生徒</option>
                <option value="parent">保護者</option>
            </select><br>
            <input type="submit" value="作成">
        </form>
    '''


@app.route('/dashboard/student')
@login_required
def dashboard_student():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    target_levels = current_user.target_levels
    
    # 科目ごとの進捗計算
    progress_summary = {}
    subjects = {
        'math': 'europe',
        'english': 'americus',
        'japanese': 'zipangu'
    }

    conquered_quest_data = []

    for sub_key, world_name in subjects.items():
        target_level = target_levels.get(sub_key, 'Lv1')
        
        # 1. ターゲットレベルの全クエストを取得
        all_quests_in_level = safe_query_all(Quest.query.filter_by(title=sub_key, level=target_level))
        total_count = len(all_quests_in_level)
        
        # 2. その中からクリア済みのものを取得
        quest_ids = [q.id for q in all_quests_in_level]
        cleared_records = safe_query_all(UserProgress.query.filter(
            UserProgress.user_id == current_user.id,
            UserProgress.status == 'cleared',
            UserProgress.quest_id.in_(quest_ids)
        ))
        cleared_count = len(cleared_records)
        cleared_quest_ids = [p.quest_id for p in cleared_records]

        # 3. 割合計算
        percentage = int((cleared_count / total_count * 100)) if total_count > 0 else 0
        
        # 4. マップ表示用の詳細データ収集 (ターゲットレベルのもののみ)
        if cleared_quest_ids:
            histories = safe_query_all(QuestHistory.query.filter(
                QuestHistory.user_id == current_user.id,
                QuestHistory.quest_id.in_(cleared_quest_ids)
            ))
            attempts_map = {h.quest_id: h.attempts for h in histories}
            
            for q_id in cleared_quest_ids:
                # SVGのIDと一致させるため、(ID % 1000) // 10 に変換
                map_marker_id = (q_id % 1000) // 10
                conquered_quest_data.append({
                    "quest_id": map_marker_id,
                    "attempts": attempts_map.get(q_id, 0),
                    "map_type": world_name
                })
        
        progress_summary[sub_key] = {
            "cleared": cleared_count,
            "total": total_count,
            "percentage": percentage,
            "level": target_level
        }

    return render_template(
        'dashboard_student.html',
        user_id=current_user.id, 
        conquered_quest_data=conquered_quest_data,
        progress_summary=progress_summary
    )

@app.route('/dashboard/parent')
@login_required
def dashboard_parent():
    if session.get('role') != 'parent':
        return redirect(url_for('login'))
    return render_template('dashboard_parent.html', user_id=session.get('user_id'))

@app.route('/dashboard/admin')
@login_required
def dashboard_admin():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('dashboard_admin.html', user_id=session.get('user_id'))

@app.route('/dashboard/teacher')
@login_required
def dashboard_teacher():
    if session.get('role') != 'teacher':
        return redirect(url_for('login'))
    return render_template('dashboard_teacher.html', user_id=session.get('user_id'))


# タイトル一覧表示（ステップ1）
@app.route('/select_title')
@login_required
def select_title():
    titles = safe_query_all(db.session.query(Quest.title).distinct())
    # ユーザーに表示する際は、ここで日本語に変換
    jp_titles = [SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in titles]
    return render_template('select_title.html', titles=jp_titles)

# レベル選択（ステップ2）
@app.route('/select_level/<title>')
@login_required
def select_level(title):
    print(f"Title: {title}")
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    levels = safe_query_all(db.session.query(Quest.level).filter_by(title=title_key).distinct())
    print(f"Levels: {levels}")
    return render_template('select_level.html', title=title, levels=[l[0] for l in levels])

@app.route('/select_quest/<title>/<level>')
@login_required
def select_quest_by_title_level(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = safe_query_all(Quest.query.filter_by(title=title_key, level=level))

    history_map = {}
    if current_user.is_authenticated:
        user_id = current_user.id
        histories = safe_query_all(QuestHistory.query.filter(
            QuestHistory.user_id == user_id,
            QuestHistory.quest_id.in_([q.id for q in quests])
        ))
        history_map = {h.quest_id: h for h in histories}

    return render_template(
        'select_quest.html',
        title=title,
        level=level,
        quests=quests,
        history_map=history_map
    )

# クエスト実行（ステップ4）    
@app.route('/quest/<int:quest_id>', methods=['GET', 'POST'])
def quest(quest_id):
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    quest_obj = safe_get(Quest, quest_id)
    if not quest_obj:
        return "クエストが見つかりません", 404

    if request.method == 'POST':
        # 解答取得と採点
        submitted = [int(request.form.get(f'q{i}')) for i in range(len(quest_obj.questions))]
        correct = [q.answer for q in quest_obj.questions]
        score = sum([1 for i, ans in enumerate(submitted) if ans == correct[i]])

        # 結果表示へ
        return render_template(
            'quest_result.html',
            score=score,
            total=len(correct),
            cleared=(score == len(correct)),
            quest_id=quest_id
        )

    return render_template('quest_run.html', quest=quest_obj, quest_id=quest_id)

@app.route("/quest/select/<title>/<level>")
def select_quest(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = safe_query_all(Quest.query.filter_by(title=title_key, level=level))
    print(quests)
    return render_template(
        'select_quest.html',
        title=title,
        level=level,
        quests=quests
    )

@app.route("/quest/run/<int:quest_id>")
def quest_run(quest_id):
    quest = safe_get(Quest, quest_id)
    if not quest:
        return "指定されたクエストが存在しません", 404

    # すべての同タイトルの問題を取得（1問＝1レコード）
    quest = safe_query_first(Quest.query.filter_by(id=quest_id))  # ✅ 1件のQuestオブジェクトになる
    if not quest:
        return "クエストが見つかりません", 404

    all_questions = quest.questions  # Question オブジェクトのリスト

    questions = []

    for q in all_questions:
        choices = None
        if q.type == 'choice':
            # q.choicesが文字列のJSONならパースする
            try:
                choices = json.loads(q.choices)
                random.shuffle(choices)  # 選択肢をシャッフル
            except Exception:
                choices = q.choices  # パースできなければそのまま
        else:
            try:
                choices = json.loads(q.choices)
            except Exception:
                choices = q.choices

        # q.answerが文字列のJSONならパースする
        try:
            answer = json.loads(q.answer)
        except Exception:
            answer = q.answer  # パースできなければそのまま

        # すでに構造化されていないので、自前で構築
        if q.type == 'svg_interactive' or q.type == 'figure_choice':
            # Try to parse choices as JSON (new format with 'svg' and 'ggb')
            svg_display = q.choices
            try:
                choices_json = json.loads(q.choices)
                if isinstance(choices_json, dict) and 'svg' in choices_json:
                    svg_display = choices_json['svg']
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                sub_questions = json.loads(q.answer) if q.answer else []
                # figure_choice の場合は各小問の選択肢をシャッフル
                if q.type == 'figure_choice':
                    for sub_q in sub_questions:
                        if 'choices' in sub_q and isinstance(sub_q['choices'], list):
                            random.shuffle(sub_q['choices'])
            except json.JSONDecodeError:
                sub_questions = []

            questions.append({
                "type": q.type,
                "text": q.text,
                "choices": q.choices, # Pass raw JSON for size extraction in template
                "svg_content": svg_display,
                "sub_questions": sub_questions
            })
        elif q.type == 'function_graph':
            questions.append({
                "type": q.type,
                "text": q.text,
                "answer": answer, # This will be the parsed list of dicts
                "choices": choices,
                "answers": None
            })
        elif q.type == 'function_graph_choice':
            # q.choices is now an object containing {'definitions': [...], 'width': ..., 'height': ...}
            try:
                choices_parsed = json.loads(q.choices) if q.choices else {}
                if isinstance(choices_parsed, dict):
                    graph_data = choices_parsed
                else:
                    # Legacy support: if it was just a list, keep it as definitions
                    graph_data = {'definitions': choices_parsed, 'width': '', 'height': ''}
            except json.JSONDecodeError:
                graph_data = {'definitions': [], 'width': '', 'height': ''}

            try:
                sub_questions = json.loads(q.answer) if q.answer else []
                # 各小問の選択肢をシャッフル
                for sub_q in sub_questions:
                    if 'choices' in sub_q and isinstance(sub_q['choices'], list):
                        random.shuffle(sub_q['choices'])
            except json.JSONDecodeError:
                sub_questions = []

            questions.append({
                "type": q.type,
                "text": q.text,
                "graph_data": graph_data,
                "sub_questions": sub_questions,
                "explanation": q.explanation
            })
        elif q.type == 'english_reading':
            try:
                word_list_data = json.loads(q.choices) if q.choices else {'word_list': []}
            except Exception:
                word_list_data = {'word_list': []}

            try:
                sub_questions = json.loads(q.answer) if q.answer else []
                for sub_q in sub_questions:
                    if 'choices' in sub_q and isinstance(sub_q['choices'], list):
                        random.shuffle(sub_q['choices'])
            except Exception:
                sub_questions = []

            questions.append({
                "type": q.type,
                "text": q.text,
                "word_list": word_list_data.get('word_list', []),
                "sub_questions": sub_questions,
                "explanation": q.explanation
            })
        else:
            questions.append({
                "type": q.type,  
                "text": q.text,
                "choices": choices,
                "answer": answer if q.type != "numeric" else None,
                "answers": answer if q.type == "numeric" else None
            })

    # Get title and level from request args if present (from manage_quests)
    # Otherwise, use the quest's own title/level as fallback
    # Store original keys in session for managing redirects back to filtered lists
    param_title = request.args.get('title')
    param_level = request.args.get('level')
    
    app.logger.debug(f"[quest_run] Received title: {param_title}, level: {param_level}")

    if param_title and param_level:
        session['last_manage_quests_filters'] = {'title': param_title, 'level': param_level}
        app.logger.debug(f"[quest_run] Stored in session: {session['last_manage_quests_filters']}")

    return render_template(
        "quest_run.html",
        quest_id=quest_id,
        quest=quest,
        title=SUBJECT_KEY_TO_JP.get(quest.title, quest.title), # For display
        level=quest.level, # For display
        questions=questions,
        role=session.get('role'),
        original_title=param_title or quest.title, # Pass original title/level for "back" links
        original_level=param_level or quest.level
    )

# クエストの結果を処理するエンドポイント
@app.route('/quest/<int:quest_id>/result', methods=['GET', 'POST'])
def quest_result(quest_id):
    if request.method == 'POST':
        quest = safe_get(Quest, quest_id)
        if not quest:
            return "Quest not found", 404

        results = []
        for i, q in enumerate(quest.questions):
            question_type = q.type
            correct = False
            user_answer = ''
            expected = ''

            if question_type == 'choice':
                user_answer = request.form.get(f'q{i}', '').strip()
                try:
                    correct_answer = json.loads(q.answer)
                except (json.JSONDecodeError, TypeError):
                    correct_answer = q.answer

                if isinstance(correct_answer, (int, float, bool)):
                    correct_answer = str(correct_answer)
                if isinstance(correct_answer, str):
                    correct_answer = correct_answer.strip()

                correct = user_answer == correct_answer
                expected = correct_answer

            elif question_type == 'multiple_choice':
                user_answers = request.form.getlist(f'q{i}')
                try:
                    # DBの答えはカンマ区切りの文字列
                    correct_answers = [ans.strip() for ans in q.answer.split(',')]
                except Exception:
                    correct_answers = []
                
                # ソートして比較
                correct = sorted(user_answers) == sorted(correct_answers)
                user_answer = ','.join(sorted(user_answers))
                expected = ','.join(sorted(correct_answers))

            elif question_type == 'sort':
                user_answer = request.form.get(f'q{i}', '').strip()
                try:
                    correct_answer = json.loads(q.answer)
                except (json.JSONDecodeError, TypeError):
                    correct_answer = q.answer
                if isinstance(correct_answer, str):
                    correct_answer = correct_answer.strip()
                
                # 句読点の前のスペースを削除して正規化
                user_answer_normalized = user_answer.replace(" .", ".").replace(" ,", ",").replace(" ?", "?").replace(" !", "!")
                correct_answer_normalized = str(correct_answer).replace(" .", ".").replace(" ,", ",").replace(" ?", "?").replace(" !", "!")
                
                correct = user_answer_normalized.lower() == correct_answer_normalized.lower()
                expected = correct_answer

            elif question_type == 'fill_in_the_blank_en':
                user_answer = request.form.get(f'q{i}', '').strip().lower()
                try:
                    # Load answer which might be a JSON string
                    correct_answers_raw = json.loads(q.answer)
                except (json.JSONDecodeError, TypeError):
                    # Or a plain string
                    correct_answers_raw = q.answer

                # NEW: Check if correct_answers_raw is not None before splitting
                if correct_answers_raw:
                    # Split the string by comma to get multiple answers, and trim whitespace from each
                    correct_answer_list = [ans.strip().lower() for ans in correct_answers_raw.split(',')]
                else:
                    correct_answer_list = []

                # Check if the user's answer is in the list of correct answers
                correct = user_answer in correct_answer_list
                expected = correct_answers_raw # Show all possible answers in the result

            elif question_type == 'svg_interactive':
                sub_questions = json.loads(q.answer)
                all_sub_correct = True
                user_answers_list = []
                expected_answers_list = []
                for sub_q in sub_questions:
                    sub_q_id = sub_q['id']
                    form_field_name = f"q{i}_{sub_q_id}"
                    user_val = request.form.get(form_field_name, '').strip()
                    expected_val = str(sub_q['answer']).strip()
                    user_answers_list.append({sub_q['prompt']: user_val})
                    expected_answers_list.append({sub_q['prompt']: expected_val})
                    if user_val != expected_val:
                        all_sub_correct = False
                correct = all_sub_correct
                user_answer = user_answers_list
                expected = expected_answers_list

            elif question_type == 'figure_choice':
                sub_questions = json.loads(q.answer)
                all_sub_correct = True
                user_answers_list = []
                expected_answers_list = []
                for sub_q_index, sub_q in enumerate(sub_questions):
                    form_field_name = f"q{i}_{sub_q_index}"
                    user_val = request.form.get(form_field_name, '').strip()
                    expected_val = str(sub_q['answer']).strip()
                    user_answers_list.append({sub_q['prompt']: user_val})
                    expected_answers_list.append({sub_q['prompt']: expected_val})
                    if user_val != expected_val:
                        all_sub_correct = False
                correct = all_sub_correct
                user_answer = user_answers_list
                expected = expected_answers_list

            elif question_type == 'numeric':
                answer_list = json.loads(q.answer)
                user_input = []
                expected = []
                correct = True
                for j, ans in enumerate(answer_list):
                    field = f"q{i}_{j}"
                    user_val = request.form.get(field, '').strip()
                    expected_val = str(ans['answer']).strip()
                    expected.append({ans['label']: expected_val})
                    user_input.append({ans['label']: user_val})
                    if user_val != expected_val:
                        correct = False
                user_answer = user_input

            elif question_type == 'function_graph_choice':
                try:
                    sub_questions = json.loads(q.answer)
                except (json.JSONDecodeError, TypeError):
                    sub_questions = []
                
                all_sub_correct = True
                user_answers_list = []
                expected_answers_list = []
                
                for sub_q_index, sub_q in enumerate(sub_questions):
                    form_field_name = f"q{i}_{sub_q_index}"
                    user_val = request.form.get(form_field_name, '').strip()
                    expected_val = str(sub_q.get('answer', '')).strip()
                    
                    user_answers_list.append({sub_q.get('prompt', ''): user_val})
                    expected_answers_list.append({sub_q.get('prompt', ''): expected_val})
                    
                    if user_val != expected_val:
                        all_sub_correct = False
                        
                correct = all_sub_correct
                user_answer = user_answers_list
                expected = expected_answers_list

            elif question_type == 'function_graph':
                try:
                    # choices stores the sub-questions (prompts and answers) for function_graph
                    sub_questions = json.loads(q.choices) if q.choices else []
                except (json.JSONDecodeError, TypeError):
                    sub_questions = []
                
                all_sub_correct = True
                user_answers_list = []
                expected_answers_list = []
                
                for sub_q_index, sub_q in enumerate(sub_questions):
                    form_field_name = f"q{i}_{sub_q_index}"
                    user_val = request.form.get(form_field_name, '').strip()
                    expected_val = str(sub_q.get('answer', '')).strip()
                    
                    user_answers_list.append({sub_q.get('prompt', ''): user_val})
                    expected_answers_list.append({sub_q.get('prompt', ''): expected_val})
                    
                    if user_val != expected_val:
                        all_sub_correct = False
                        
                correct = all_sub_correct
                user_answer = user_answers_list
                expected = expected_answers_list
                expected = expected_answers_list

            elif question_type == 'english_reading':
                try:
                    sub_questions = json.loads(q.answer) if q.answer else []
                except (json.JSONDecodeError, TypeError):
                    sub_questions = []
                
                all_sub_correct = True
                user_answers_list = []
                expected_answers_list = []
                
                for sub_q_index, sub_q in enumerate(sub_questions):
                    form_field_name = f"q{i}_{sub_q_index}"
                    user_val = request.form.get(form_field_name, '').strip()
                    expected_val = str(sub_q.get('answer', '')).strip()
                    
                    user_answers_list.append({sub_q.get('prompt', ''): user_val})
                    expected_answers_list.append({sub_q.get('prompt', ''): expected_val})
                    
                    if user_val != expected_val:
                        all_sub_correct = False
                        
                correct = all_sub_correct
                user_answer = user_answers_list
                expected = expected_answers_list

            results.append({
                'question_id': q.id,
                'user_answer': user_answer,
                'correct': correct,
                'type': question_type,
                'expected': expected
            })

        all_correct = all(r['correct'] for r in results)

        user_id = session.get('user_id')
        if user_id:
            try:
                # Update or create QuestHistory first
                history = safe_query_first(QuestHistory.query.filter_by(user_id=user_id, quest_id=quest_id))
                if history:
                    history.attempts += 1
                    history.correct = all_correct
                    history.last_attempt = datetime.now(timezone.utc)
                    if all_correct:
                        history.cleared_count += 1
                        history.is_cleared = True
                    elif history.is_cleared:
                        history.is_cleared = True #維持
                else:
                    history = QuestHistory(
                        user_id=user_id,
                        quest_id=quest_id,
                        correct=all_correct,
                        is_cleared=all_correct,
                        cleared_count=1 if all_correct else 0,
                        attempts=1,
                        last_attempt=datetime.now(timezone.utc)
                    )
                    db.session.add(history)

                # Create a detailed log for this attempt
                score = sum(1 for r in results if r['correct'])
                total_questions = len(results)
                attempt_log = QuestAttemptLog(
                    user_id=user_id,
                    quest_id=quest_id,
                    correct_answers=score,
                    total_questions=total_questions
                )
                db.session.add(attempt_log)

                # Now, sync UserProgress based on the definitive 'is_cleared' status from QuestHistory
                if history.is_cleared:
                    progress_record = safe_query_first(UserProgress.query.filter_by(user_id=user_id, quest_id=quest_id))
                    if progress_record:
                        if progress_record.status != 'cleared':
                            progress_record.status = 'cleared'
                            progress_record.conquered_at = datetime.now(timezone.utc)
                    else:
                        new_progress = UserProgress(
                            user_id=user_id,
                            quest_id=quest_id,
                            status='cleared',
                            conquered_at=datetime.now(timezone.utc)
                        )
                        db.session.add(new_progress)
                
                safe_commit()

            except IntegrityError as e:
                db.session.rollback()
                app.logger.error(f"DATABASE SAVE ERROR: {e}")

        session['last_result'] = {
            'quest_id': quest_id,
            'results': results,
            'all_correct': all_correct
        }
        return redirect(url_for('quest_result', quest_id=quest_id))

    # GET request
    role = session.get('role')
    if not role:
        return redirect(url_for('login')) # Redirect to login if role is not in session

    last_result = session.get('last_result')
    if not last_result or last_result.get('quest_id') != quest_id:
        # Redirect to the dashboard corresponding to the user's role
        return redirect(url_for(f'dashboard_{role}'))

    quest = safe_get(Quest, quest_id)
    jp_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title)

    # Re-fetch full question objects for the template
    question_ids = [r['question_id'] for r in last_result['results']]
    questions = safe_query_all(Question.query.filter(Question.id.in_(question_ids)))
    question_map = {q.id: q for q in questions}

    # Add the full question object back into the results
    for res in last_result['results']:
        q = question_map.get(res['question_id'])
        if q:
            question_view_model = {
                'id': q.id,
                'type': q.type,
                'text': q.text,
                'choices': q.choices,
                'explanation': q.explanation
            }
            if q.type == 'svg_interactive' or q.type == 'figure_choice':
                svg_display = q.choices
                try:
                    choices_json = json.loads(q.choices)
                    if isinstance(choices_json, dict) and 'svg' in choices_json:
                        svg_display = choices_json['svg']
                except (json.JSONDecodeError, TypeError):
                    pass
                question_view_model['svg_content'] = svg_display
            elif q.type == 'english_reading':
                try:
                    word_list_data = json.loads(q.choices) if q.choices else {'word_list': []}
                except Exception:
                    word_list_data = {'word_list': []}
                question_view_model['word_list'] = word_list_data.get('word_list', [])
                try:
                    question_view_model['sub_questions'] = json.loads(q.answer) if q.answer else []
                except Exception:
                    question_view_model['sub_questions'] = []
            # Explanation is now rendered as Markdown on the client side
            res['question'] = question_view_model
    
    # Retrieve original title and level from session for filter retention
    filters = session.get('last_manage_quests_filters', {})
    app.logger.debug(f"[quest_result] Retrieved from session: {filters}")
    original_title = filters.get('title', '')
    original_level = filters.get('level', '')

    return render_template("quest_result.html",
                           quest_id=quest_id,
                           quest=quest,
                           results=last_result['results'],
                           all_correct=last_result['all_correct'],
                           title=jp_title,
                           level=quest.level,
                           role=role,
                           original_title=original_title, # Pass these to template
                           original_level=original_level)


@app.route('/quest')
def quest_list():
    return render_template('list_quests.html', quests=Quest)

# 進捗表示用ルート
@app.route('/progress')
@login_required
def progress():
    # Allow admins and parents to view a student's progress by passing user_id
    requested_user_id = request.args.get('user_id', type=int)
    
    if requested_user_id:
        if session.get('role') == 'admin':
            user_id = requested_user_id
        elif session.get('role') == 'parent':
            # Verify if the student belongs to this parent
            student = safe_get(User, requested_user_id)
            if student and student.parent_id == session.get('user_id'):
                user_id = requested_user_id
            else:
                flash("指定された生徒の進捗を見る権限がありません。")
                return redirect(url_for('dashboard'))
        else:
            flash("他のユーザーの進捗を見る権限がありません。")
            return redirect(url_for('dashboard'))
    else:
        # Default to self for students
        if session.get('role') != 'student':
            return redirect(url_for('login'))
        user_id = session.get('user_id')

    student = safe_get(User, user_id)
    if not student:
        flash("生徒が見つかりません。")
        return redirect(url_for('dashboard'))

    # 1. ユーザーがクリアした進捗レコードをすべて取得
    progress_records = safe_query_all(UserProgress.query.filter_by(user_id=user_id, status='cleared'))
    
    # ユーザーの全履歴（メダル計算用）を取得
    histories = safe_query_all(QuestHistory.query.filter_by(user_id=user_id))

    if not progress_records and not histories:
        processed_progress_data = []
    else:
        # 進捗と履歴に関連する全クエストIDを取得
        quest_ids = list(set([p.quest_id for p in progress_records] + [h.quest_id for h in histories]))
        quests = safe_query_all(Quest.query.filter(Quest.id.in_(quest_ids)))
        quest_map = {q.id: q for q in quests}

        # タイトルとレベルごとに集計
        from collections import defaultdict
        aggregated = defaultdict(lambda: {'cleared': 0, 'medals': 0})
        
        for p in progress_records:
            quest = quest_map.get(p.quest_id)
            if quest:
                aggregated[(quest.title, quest.level)]['cleared'] += 1
        
        for h in histories:
            quest = quest_map.get(h.quest_id)
            if quest:
                aggregated[(quest.title, quest.level)]['medals'] += h.attempts
        
        # 各タイトル・レベルの「全問題数」を取得してメダルを判定
        processed_progress_data = []
        for (title, level), stats in sorted(aggregated.items()):
            jp_title = SUBJECT_KEY_TO_JP.get(title, title)
            
            # その科目・レベルの総問題数を取得
            total_q_count = safe_query_first(db.session.query(func.count(Quest.id)).filter_by(title=title, level=level))[0]
            
            # メダル判定ロジック (挑戦回数 ÷ 総問題数)
            ratio = stats['medals'] / total_q_count if total_q_count > 0 else 0
            
            medal = None
            if ratio >= 2.0:
                medal = {'icon': 'fa-gem', 'color': '#00d2ff', 'label': 'ダイヤモンド', 'text': 'text-info'}
            elif ratio >= 1.5:
                medal = {'icon': 'fa-medal', 'color': '#FFD700', 'label': '金', 'text': 'text-warning'}
            elif ratio >= 1.0:
                medal = {'icon': 'fa-medal', 'color': '#C0C0C0', 'label': '銀', 'text': 'text-secondary'}
            elif ratio >= 0.5:
                medal = {'icon': 'fa-medal', 'color': '#CD7F32', 'label': '銅', 'text': 'text-brown'}

            processed_progress_data.append({
                'title': jp_title,
                'level': level,
                'cleared_count': stats['cleared'],
                'total_count': total_q_count,
                'medal_count': stats['medals'],
                'medal': medal,
                'ratio': round(ratio, 2)
            })

    # 2. New query for 4-week chart data
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
    weekly_data_raw = safe_query_all(db.session.query(
        func.strftime('%Y-%W', QuestAttemptLog.attempted_at).label('week'),
        func.sum(case((QuestAttemptLog.correct_answers == QuestAttemptLog.total_questions, 1), else_=0)).label('cleared_count'),
        func.count(QuestAttemptLog.id).label('attempt_count')
    ).filter(
        QuestAttemptLog.user_id == user_id,
        QuestAttemptLog.attempted_at >= four_weeks_ago
    ).group_by('week').order_by('week'))

    # Fill gaps for weeks
    weekly_chart_data = {'labels': [], 'cleared_count': [], 'attempt_count': []}
    weekly_map = {d.week: d for d in weekly_data_raw}
    for i in range(4, -1, -1):
        dt = datetime.now(timezone.utc) - timedelta(weeks=i)
        w_key = dt.strftime('%Y-%W')
        weekly_chart_data['labels'].append(w_key)
        if w_key in weekly_map:
            weekly_chart_data['cleared_count'].append(int(weekly_map[w_key].cleared_count or 0))
            weekly_chart_data['attempt_count'].append(int(weekly_map[w_key].attempt_count or 0))
        else:
            weekly_chart_data['cleared_count'].append(0)
            weekly_chart_data['attempt_count'].append(0)

    # 3. New query for 3-month chart data
    three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)
    monthly_data_raw = safe_query_all(db.session.query(
        func.strftime('%Y-%m', QuestAttemptLog.attempted_at).label('month'),
        func.sum(case((QuestAttemptLog.correct_answers == QuestAttemptLog.total_questions, 1), else_=0)).label('cleared_count'),
        func.count(QuestAttemptLog.id).label('attempt_count')
    ).filter(
        QuestAttemptLog.user_id == user_id,
        QuestAttemptLog.attempted_at >= three_months_ago
    ).group_by('month').order_by('month'))

    # Fill gaps for months
    monthly_chart_data = {'labels': [], 'cleared_count': [], 'attempt_count': []}
    monthly_map = {d.month: d for d in monthly_data_raw}
    for i in range(2, -1, -1):
        # Rough month subtraction
        dt = datetime.now(timezone.utc) - timedelta(days=i*30)
        m_key = dt.strftime('%Y-%m')
        monthly_chart_data['labels'].append(m_key)
        if m_key in monthly_map:
            monthly_chart_data['cleared_count'].append(int(monthly_map[m_key].cleared_count or 0))
            monthly_chart_data['attempt_count'].append(int(monthly_map[m_key].attempt_count or 0))
        else:
            monthly_chart_data['cleared_count'].append(0)
            monthly_chart_data['attempt_count'].append(0)

    return render_template(
        "progress.html", 
        student=student,
        progress_data=processed_progress_data,
        weekly_chart_data=weekly_chart_data,
        monthly_chart_data=monthly_chart_data
    )

@app.route('/admin/students')
def manage_students():
    # ログインしているユーザーが管理者かチェック（適宜修正）
    if session.get('role') != 'admin' :
        return redirect(url_for('login'))

    users = safe_query_all(User.query.filter_by(role='student'))

    data = []

    for user in users:
        user_data = {
            'id': user.id,
            'username': user.username,
            'nickname': user.nickname,
            'progress': [],
            'medals': [],
            'parent': None
        }
        
        # 保護者情報の取得
        if user.parent:
            user_data['parent'] = {
                'id': user.parent.id,
                'username': user.parent.username,
                'nickname': user.parent.nickname
            }

        # 学習進捗状況の取得（UserProgressから）
        progress_records = safe_query_all(UserProgress.query.filter_by(user_id=user.id, status='cleared'))
        if not progress_records:
            user_data['progress'] = []
        else:
            quest_ids = list(set(p.quest_id for p in progress_records))
            quests = safe_query_all(Quest.query.filter(Quest.id.in_(quest_ids)))
            quest_map = {q.id: q for q in quests}

            from collections import defaultdict
            aggregated = defaultdict(int)
            for p in progress_records:
                quest = quest_map.get(p.quest_id)
                if quest:
                    key = (quest.title, quest.level)
                    aggregated[key] += 1
            
            processed_progress = []
            for (title, level), count in sorted(aggregated.items()):
                jp_title = SUBJECT_KEY_TO_JP.get(title, title)
                processed_progress.append({'title': jp_title, 'level': level, 'count': count})
            user_data['progress'] = processed_progress

        # メダル取得状況の取得（挑戦回数の合計）
        medal_counts = safe_query_all(db.session.query(
            QuestHistory.quest_id,
            QuestHistory.attempts
        ).filter_by(user_id=user.id))

        user_data['medals'] = [{'quest_id': m[0], 'count': m[1]} for m in medal_counts]

        data.append(user_data)

    # 全保護者のリストを取得（紐付け用）
    all_parents = safe_query_all(User.query.filter_by(role='parent'))
    parent_list = [{'id': p.id, 'username': p.username, 'nickname': p.nickname} for p in all_parents]

    return render_template('manage_students.html', students=data, parents=parent_list)

@app.route('/admin/user/edit/<int:user_id>', methods=['GET'])
@login_required
def edit_user_admin(user_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    user = safe_get(User, user_id)
    if not user:
        abort(404)
        
    return render_template('edit_user_admin.html', user=user)

@app.route('/admin/user/update/<int:user_id>', methods=['POST'])
@login_required
def update_user_admin(user_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    user = safe_get(User, user_id)
    if not user:
        abort(404)
        
    user.nickname = request.form.get('nickname')
    password = request.form.get('password')
    if password:
        user.set_password(password)
    
    safe_commit()
    flash(f"{user.username} の設定を更新しました。", "success")
    
    if user.role == 'teacher':
        return redirect(url_for('manage_teachers'))
    elif user.role == 'admin':
        return redirect(url_for('manage_admins'))
    else:
        return redirect(url_for('manage_students'))


@app.route('/admin/user/add', methods=['POST'])
@login_required
def add_student_with_parent():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    # 生徒情報
    s_username = request.form.get('student_username')
    s_nickname = request.form.get('student_nickname')
    s_password = request.form.get('student_password')
    
    # 保護者情報 (既存)
    existing_parent_id = request.form.get('existing_parent_id')
    
    # 保護者情報 (新規用)
    p_username = request.form.get('parent_username')
    p_nickname = request.form.get('parent_nickname')
    p_password = request.form.get('parent_password')

    try:
        # 生徒作成
        student = User(username=s_username, nickname=s_nickname, role='student')
        student.set_password(s_password)
        db.session.add(student)
        
        # 既存の保護者が選択されている場合
        if existing_parent_id:
            student.parent_id = int(existing_parent_id)
        # 新規保護者作成（入力がある場合）
        elif p_username and p_password:
            # 既存の保護者がいないか確認（念のためユーザー名で）
            parent = safe_query_first(User.query.filter_by(username=p_username, role='parent'))
            if not parent:
                parent = User(username=p_username, nickname=p_nickname or p_username, role='parent')
                parent.set_password(p_password)
                db.session.add(parent)
                db.session.flush() # ID確定のため
            
            student.parent_id = parent.id
        
        safe_commit()
        flash(f"生徒 {s_username} を登録しました", "success")
    except IntegrityError:
        db.session.rollback()
        flash("エラー: ユーザー名が既に存在します", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"エラー: {str(e)}", "danger")

    return redirect(url_for('manage_students'))

@app.route('/admin/admins')
@login_required
def manage_admins():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    admins = safe_query_all(User.query.filter_by(role='admin'))
    return render_template('manage_admins.html', admins=admins)

@app.route('/admin/admin/add', methods=['POST'])
@login_required
def add_admin():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    username = request.form.get('username')
    nickname = request.form.get('nickname')
    password = request.form.get('password')
    
    if safe_query_first(User.query.filter_by(username=username)):
        flash("そのユーザー名は既に使用されています。", "danger")
        return redirect(url_for('manage_admins'))
        
    admin = User(username=username, nickname=nickname, role='admin')
    admin.set_password(password)
    db.session.add(admin)
    safe_commit()
    flash(f"管理者 {username} を登録しました。", "success")
    return redirect(url_for('manage_admins'))

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    if user_id == current_user.id:
        flash("自分自身を削除することはできません。", "danger")
        return redirect(request.referrer or url_for('manage_students'))
    
    user = safe_get(User, user_id)
    if not user:
        abort(404)
    username = user.username
    role = user.role

    try:
        # 関連データの削除（生徒の場合）
        if role == 'student':
            UserProgress.query.filter_by(user_id=user_id).delete()
            QuestHistory.query.filter_by(user_id=user_id).delete()
            QuestAttemptLog.query.filter_by(user_id=user_id).delete()
        
        # 保護者の場合、子供たちのparent_idをNULLにする
        elif role == 'parent':
            children = safe_query_all(User.query.filter_by(parent_id=user_id))
            for child in children:
                child.parent_id = None

        db.session.delete(user)
        safe_commit()
        flash(f"ユーザー {username} ({role}) を削除しました", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除エラー: {str(e)}", "danger")

    return redirect(request.referrer or url_for('manage_students'))

@app.route('/admin/teachers')
@login_required
def manage_teachers():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    teachers = safe_query_all(User.query.filter_by(role='teacher'))
    return render_template('manage_teachers.html', teachers=teachers)

@app.route('/admin/teacher/add', methods=['POST'])
@login_required
def add_teacher():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    username = request.form.get('username')
    nickname = request.form.get('nickname')
    password = request.form.get('password')
    
    if safe_query_first(User.query.filter_by(username=username)):
        flash("そのユーザー名は既に使用されています。", "danger")
        return redirect(url_for('manage_teachers'))
        
    teacher = User(username=username, nickname=nickname, role='teacher')
    teacher.set_password(password)
    db.session.add(teacher)
    safe_commit()
    flash(f"教師 {username} を登録しました。", "success")
    return redirect(url_for('manage_teachers'))


# ==================================================
# ユーザー情報のJSONエクスポート・インポート
# ==================================================

def parse_datetime(dt_str):
    if not dt_str:
        return None
    try:
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return datetime.fromisoformat(dt_str)
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def serialize_user(user):
    return {
        'username': user.username,
        'nickname': user.nickname,
        'password_hash': user.password_hash,
        'role': user.role,
        'is_first_login': user.is_first_login,
        'avatar': user.avatar,
        'user_level': user.user_level,
        'medals': user.medals,
        'user_title': user.user_title,
        'target_levels_json': user.target_levels_json,
    }

def export_student_data(student):
    parent_data = None
    if student.parent:
        parent_data = serialize_user(student.parent)
    
    # Progress records
    progress_records = safe_query_all(UserProgress.query.filter_by(user_id=student.id))
    progress_data = []
    for p in progress_records:
        progress_data.append({
            'quest_id': p.quest_id,
            'status': p.status,
            'conquered_at': p.conquered_at.isoformat() if p.conquered_at else None
        })
        
    # Quest history records
    history_records = safe_query_all(QuestHistory.query.filter_by(user_id=student.id))
    history_data = []
    for h in history_records:
        history_data.append({
            'quest_id': h.quest_id,
            'correct': h.correct,
            'is_cleared': h.is_cleared,
            'cleared_count': h.cleared_count,
            'attempts': h.attempts,
            'last_attempt': h.last_attempt.isoformat() if h.last_attempt else None
        })
        
    # Quest attempt logs
    attempt_logs = safe_query_all(QuestAttemptLog.query.filter_by(user_id=student.id))
    attempt_logs_data = []
    for log in attempt_logs:
        attempt_logs_data.append({
            'quest_id': log.quest_id,
            'correct_answers': log.correct_answers,
            'total_questions': log.total_questions,
            'attempted_at': log.attempted_at.isoformat() if log.attempted_at else None
        })
        
    student_record = serialize_user(student)
    student_record['parent'] = parent_data
    student_record['progress'] = progress_data
    student_record['history'] = history_data
    student_record['attempt_logs'] = attempt_logs_data
    
    return student_record

@app.route('/admin/students/export')
@login_required
def export_students():
    if not current_user.is_admin():
        return redirect(url_for('login'))
        
    students = safe_query_all(User.query.filter_by(role='student'))
    export_data = [export_student_data(student) for student in students]
    
    json_content = json.dumps(export_data, indent=4, ensure_ascii=False)
    response = Response(
        json_content,
        mimetype="application/json",
        headers={"Content-disposition": "attachment; filename=students_export.json"}
    )
    return response

@app.route('/admin/student/export/<int:user_id>')
@login_required
def export_single_student(user_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))
        
    student = safe_get(User, user_id)
    if not student or student.role != 'student':
        abort(404)
        
    export_data = export_student_data(student)
    
    json_content = json.dumps(export_data, indent=4, ensure_ascii=False)
    filename = f"student_{student.username}_export.json"
    response = Response(
        json_content,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )
    return response

@app.route('/admin/students/import', methods=['POST'])
@login_required
def import_students():
    if not current_user.is_admin():
        abort(403)
        
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("JSONファイルを選択してください", "danger")
        return redirect(url_for('manage_students'))
        
    try:
        if not file.filename.lower().endswith('.json'):
            flash("サポートされていないファイル形式です (.json を使用してください)", "danger")
            return redirect(url_for('manage_students'))
            
        raw_data = json.loads(file.read().decode('utf-8'))
        if isinstance(raw_data, dict):
            records = [raw_data]
        elif isinstance(raw_data, list):
            records = raw_data
        else:
            flash("無効なJSONフォーマットです。", "danger")
            return redirect(url_for('manage_students'))
            
        success_count = 0
        error_count = 0
        
        for record in records:
            # 1. Create or update parent if present
            parent_id = None
            parent_data = record.get('parent')
            if parent_data:
                p_username = parent_data.get('username')
                if p_username:
                    parent = safe_query_first(User.query.filter_by(username=p_username))
                    if not parent:
                        p_pw_hash = parent_data.get('password_hash')
                        if not p_pw_hash:
                            p_pw_hash = generate_password_hash("password")
                        parent = User(
                            username=p_username,
                            role='parent',
                            nickname=parent_data.get('nickname') or p_username,
                            password_hash=p_pw_hash,
                            avatar=parent_data.get('avatar'),
                            is_first_login=parent_data.get('is_first_login', True),
                        )
                        db.session.add(parent)
                        db.session.flush() # get parent.id
                    else:
                        if 'nickname' in parent_data:
                            parent.nickname = parent_data['nickname']
                        if 'password_hash' in parent_data:
                            parent.password_hash = parent_data['password_hash']
                        if 'avatar' in parent_data:
                            parent.avatar = parent_data['avatar']
                        if 'is_first_login' in parent_data:
                            parent.is_first_login = parent_data['is_first_login']
                    parent_id = parent.id

            # 2. Create or update student
            s_username = record.get('username')
            if not s_username:
                error_count += 1
                continue
                
            student = safe_query_first(User.query.filter_by(username=s_username))
            if not student:
                s_pw_hash = record.get('password_hash')
                if not s_pw_hash:
                    s_pw_hash = generate_password_hash("password")
                student = User(
                    username=s_username,
                    role='student',
                    nickname=record.get('nickname') or s_username,
                    password_hash=s_pw_hash,
                    avatar=record.get('avatar'),
                    is_first_login=record.get('is_first_login', True),
                    user_level=record.get('user_level', 1),
                    medals=record.get('medals', 0),
                    user_title=record.get('user_title', '見習い'),
                    target_levels_json=record.get('target_levels_json', '{"math": "Lv1", "english": "Lv1", "japanese": "Lv1"}'),
                    parent_id=parent_id
                )
                db.session.add(student)
                db.session.flush() # get student.id
            else:
                student.role = 'student'
                if 'nickname' in record:
                    student.nickname = record['nickname']
                if 'password_hash' in record:
                    student.password_hash = record['password_hash']
                if 'avatar' in record:
                    student.avatar = record['avatar']
                if 'is_first_login' in record:
                    student.is_first_login = record['is_first_login']
                if 'user_level' in record:
                    student.user_level = record['user_level']
                if 'medals' in record:
                    student.medals = record['medals']
                if 'user_title' in record:
                    student.user_title = record['user_title']
                if 'target_levels_json' in record:
                    student.target_levels_json = record['target_levels_json']
                if parent_id is not None:
                    student.parent_id = parent_id

            # 3. Import user_progress
            progress_list = record.get('progress', [])
            for p_record in progress_list:
                quest_id = p_record.get('quest_id')
                if not quest_id:
                    continue
                status = p_record.get('status', 'unlocked')
                conquered_at = parse_datetime(p_record.get('conquered_at'))
                
                up = safe_query_first(UserProgress.query.filter_by(user_id=student.id, quest_id=quest_id))
                if not up:
                    up = UserProgress(
                        user_id=student.id,
                        quest_id=quest_id,
                        status=status,
                        conquered_at=conquered_at
                    )
                    db.session.add(up)
                else:
                    up.status = status
                    if conquered_at:
                        up.conquered_at = conquered_at

            # 4. Import quest_history
            history_list = record.get('history', [])
            for h_record in history_list:
                quest_id = h_record.get('quest_id')
                if not quest_id:
                    continue
                correct = h_record.get('correct', False)
                is_cleared = h_record.get('is_cleared', False)
                cleared_count = h_record.get('cleared_count', 0)
                attempts = h_record.get('attempts', 0)
                last_attempt = parse_datetime(h_record.get('last_attempt'))
                
                qh = safe_query_first(QuestHistory.query.filter_by(user_id=student.id, quest_id=quest_id))
                if not qh:
                    qh = QuestHistory(
                        user_id=student.id,
                        quest_id=quest_id,
                        correct=correct,
                        is_cleared=is_cleared,
                        cleared_count=cleared_count,
                        attempts=attempts,
                        last_attempt=last_attempt
                    )
                    db.session.add(qh)
                else:
                    qh.correct = correct
                    qh.is_cleared = is_cleared
                    qh.cleared_count = cleared_count
                    qh.attempts = attempts
                    if last_attempt:
                        qh.last_attempt = last_attempt

            # 5. Import quest_attempt_logs
            attempt_logs = record.get('attempt_logs', [])
            for log_record in attempt_logs:
                quest_id = log_record.get('quest_id')
                if not quest_id:
                    continue
                correct_answers = log_record.get('correct_answers', 0)
                total_questions = log_record.get('total_questions', 0)
                attempted_at = parse_datetime(log_record.get('attempted_at'))
                
                existing_log = None
                if attempted_at:
                    existing_log = safe_query_first(QuestAttemptLog.query.filter_by(
                        user_id=student.id,
                        quest_id=quest_id,
                        attempted_at=attempted_at
                    ))
                if not existing_log:
                    log = QuestAttemptLog(
                        user_id=student.id,
                        quest_id=quest_id,
                        correct_answers=correct_answers,
                        total_questions=total_questions,
                        attempted_at=attempted_at or datetime.now(timezone.utc)
                    )
                    db.session.add(log)
            
            success_count += 1
            
        safe_commit()
        if error_count > 0:
            flash(f"生徒情報のインポート完了: 成功 {success_count}件, 失敗 {error_count}件", "warning")
        else:
            flash(f"{success_count}件の生徒情報を正常にインポートしました", "success")
            
    except Exception as e:
        db.session.rollback()
        flash(f"インポートエラー: {str(e)}", "danger")
        
    return redirect(url_for('manage_students'))

@app.route('/admin/teachers/export')
@login_required
def export_teachers():
    if not current_user.is_admin():
        return redirect(url_for('login'))
        
    teachers = safe_query_all(User.query.filter_by(role='teacher'))
    export_data = [serialize_user(teacher) for teacher in teachers]
    
    json_content = json.dumps(export_data, indent=4, ensure_ascii=False)
    response = Response(
        json_content,
        mimetype="application/json",
        headers={"Content-disposition": "attachment; filename=teachers_export.json"}
    )
    return response

@app.route('/admin/teacher/export/<int:user_id>')
@login_required
def export_single_teacher(user_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))
        
    teacher = safe_get(User, user_id)
    if not teacher or teacher.role != 'teacher':
        abort(404)
        
    export_data = serialize_user(teacher)
    
    json_content = json.dumps(export_data, indent=4, ensure_ascii=False)
    filename = f"teacher_{teacher.username}_export.json"
    response = Response(
        json_content,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )
    return response

@app.route('/admin/teachers/import', methods=['POST'])
@login_required
def import_teachers():
    if not current_user.is_admin():
        abort(403)
        
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("JSONファイルを選択してください", "danger")
        return redirect(url_for('manage_teachers'))
        
    try:
        if not file.filename.lower().endswith('.json'):
            flash("サポートされていないファイル形式です (.json を使用してください)", "danger")
            return redirect(url_for('manage_teachers'))
            
        raw_data = json.loads(file.read().decode('utf-8'))
        if isinstance(raw_data, dict):
            records = [raw_data]
        elif isinstance(raw_data, list):
            records = raw_data
        else:
            flash("無効なJSONフォーマットです。", "danger")
            return redirect(url_for('manage_teachers'))
            
        success_count = 0
        error_count = 0
        
        for record in records:
            t_username = record.get('username')
            if not t_username:
                error_count += 1
                continue
                
            teacher = safe_query_first(User.query.filter_by(username=t_username))
            if not teacher:
                t_pw_hash = record.get('password_hash')
                if not t_pw_hash:
                    t_pw_hash = generate_password_hash("password")
                teacher = User(
                    username=t_username,
                    role='teacher',
                    nickname=record.get('nickname') or t_username,
                    password_hash=t_pw_hash,
                    avatar=record.get('avatar'),
                    is_first_login=record.get('is_first_login', True),
                    user_level=record.get('user_level', 1),
                    medals=record.get('medals', 0),
                    user_title=record.get('user_title', '見習い'),
                    target_levels_json=record.get('target_levels_json', '{"math": "Lv1", "english": "Lv1", "japanese": "Lv1"}')
                )
                db.session.add(teacher)
            else:
                teacher.role = 'teacher'
                if 'nickname' in record:
                    teacher.nickname = record['nickname']
                if 'password_hash' in record:
                    teacher.password_hash = record['password_hash']
                if 'avatar' in record:
                    teacher.avatar = record['avatar']
                if 'is_first_login' in record:
                    teacher.is_first_login = record['is_first_login']
                    
            success_count += 1
            
        safe_commit()
        if error_count > 0:
            flash(f"教師情報のインポート完了: 成功 {success_count}件, 失敗 {error_count}件", "warning")
        else:
            flash(f"{success_count}件の教師情報を正常にインポートしました", "success")
            
    except Exception as e:
        db.session.rollback()
        flash(f"インポートエラー: {str(e)}", "danger")
        
    return redirect(url_for('manage_teachers'))


# クエストの一覧　追加・削除
@app.route('/manage_quests')
@login_required
def manage_quests():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return redirect(url_for(f"dashboard_{current_user.role}"))

    selected_title_jp = request.args.get('title', '')
    selected_level = request.args.get('level', '')

    # 全てのユニークなタイトルを取得
    all_titles_raw = safe_query_all(db.session.query(Quest.title).distinct())
    jp_titles = sorted(list(set([SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in all_titles_raw])))

    # 全てのユニークなレベルを取得
    all_levels_raw = safe_query_all(db.session.query(Quest.level).distinct())
    all_levels = sorted(list(set([l[0] for l in all_levels_raw])))

    # 科目ごとのレベルマッピングを作成
    title_to_levels = {}
    for jp_title in jp_titles:
        title_key = SUBJECT_JP_TO_KEY.get(jp_title, jp_title)
        levels_raw = safe_query_all(db.session.query(Quest.level).filter_by(title=title_key).distinct())
        title_to_levels[jp_title] = sorted(list(set([l[0] for l in levels_raw])))

    quest_query = Quest.query
    if selected_title_jp:
        title_key = SUBJECT_JP_TO_KEY.get(selected_title_jp, selected_title_jp)
        quest_query = quest_query.filter_by(title=title_key)
    
    if selected_level:
        quest_query = quest_query.filter_by(level=selected_level)
    
    quests = safe_query_all(quest_query)

    return render_template('list_quests.html', 
                           quests=quests, 
                           titles=jp_titles, 
                           selected_title=selected_title_jp,
                           levels=all_levels,
                           all_levels_list=all_levels,
                           title_to_levels=title_to_levels,
                           selected_level=selected_level)

#　クエストの編集・問題の追加
@app.route('/admin/quests/action', methods=['POST'])
@login_required
def handle_quest_action():
    action = request.form.get('action')
    quest_ids = request.form.getlist('quest_id')
    title = request.form.get('title', '')
    level = request.form.get('level', '')

    if action == 'add':
        # Assuming 'add' goes to a new quest page that should also know how to get back
        return redirect(url_for('edit_quest', quest_id='new', title=title, level=level))
    
    # Actions that need at least one quest_id
    if not quest_ids:
        flash("Questを選択してください", "warning")
        return redirect(url_for('manage_quests', title=title, level=level))

    if action == 'edit':
        return redirect(url_for('edit_quest', quest_id=quest_ids[0], title=title, level=level))
    elif action == 'export_json':
        export_filename = request.form.get('export_filename', 'questions_export.json').strip()
        if not export_filename.endswith('.json'):
            export_filename += '.json'

        selected_quests = safe_query_all(Quest.query.filter(Quest.id.in_(quest_ids)).order_by(Quest.id))
        
        export_data = []
        for quest in selected_quests:
            # 1. Output Quest metadata record
            export_data.append({
                'record_type': 'quest',
                'id': quest.id,
                'title': quest.title,
                'level': quest.level,
                'questname': quest.questname
            })
            
            # 2. Output Question records for this quest
            questions = safe_query_all(Question.query.filter_by(quest_id=quest.id).order_by(Question.id))
            for q in questions:
                q_data = {
                    'record_type': 'question',
                    'id': q.id,
                    'quest_id': q.quest_id,
                    'type': q.type,
                    'text': q.text,
                    'explanation': q.explanation
                }
                
                try:
                    q_data['choices'] = json.loads(q.choices) if q.choices else None
                except (json.JSONDecodeError, TypeError):
                    q_data['choices'] = q.choices

                try:
                    q_data['answer'] = json.loads(q.answer) if q.answer else None
                except (json.JSONDecodeError, TypeError):
                    q_data['answer'] = q.answer
                
                export_data.append(q_data)
        
        json_content = json.dumps(export_data, indent=4, ensure_ascii=False)
        
        response = Response(
            json_content,
            mimetype="application/json",
            headers={"Content-disposition": f"attachment; filename={export_filename}"}
        )
        return response
    elif action == 'bulk_edit':
        return redirect(url_for('bulk_edit_ids', quest_ids=','.join(quest_ids), title=title, level=level))
    elif action == 'challenge':
        # Preserve title and level filters when challenging a quest from manage_quests
        return redirect(url_for('quest_run', quest_id=quest_ids[0], title=title, level=level))
    elif action == 'delete':
        deleted_count = 0
        for qid in quest_ids:
            quest_id_to_delete = int(qid)
            quest = safe_get(Quest, quest_id_to_delete)
            if quest:
                # Manually delete dependent records to prevent IntegrityError
                UserProgress.query.filter_by(quest_id=quest_id_to_delete).delete()
                QuestHistory.query.filter_by(quest_id=quest_id_to_delete).delete()
                Question.query.filter_by(quest_id=quest_id_to_delete).delete()
                QuestAttemptLog.query.filter_by(quest_id=quest_id_to_delete).delete()

                db.session.delete(quest)
                deleted_count += 1
        
        if deleted_count > 0:
            safe_commit()
            flash(f"{deleted_count}件のクエストを削除しました", "success")
        return redirect(url_for('manage_quests', title=title, level=level))
    
    # Fallback just in case
    return redirect(url_for('manage_quests', title=title, level=level))

def _update_quest_id_internal(old_id, new_id):
    """Internal helper to update quest ID across all related tables."""
    user_tables = ["quest_attempt_logs", "quest_history", "user_progress"]
    content_tables = ["questions", "quests"]

    # ユーザーDB側の更新
    for table in user_tables:
        column = "quest_id"
        db.session.execute(db.text(f"UPDATE {table} SET {column} = :new_id WHERE {column} = :old_id"),
                           {'new_id': new_id, 'old_id': old_id})
    
    # コンテンツDB側の更新
    content_engine = db.get_engine(app, bind='content')
    for table in content_tables:
        column = "id" if table == "quests" else "quest_id"
        db.session.execute(db.text(f"UPDATE {table} SET {column} = :new_id WHERE {column} = :old_id"),
                           {'new_id': new_id, 'old_id': old_id},
                           bind_arguments={'bind': content_engine})

@app.route('/admin/quest/bulk_edit_ids', methods=['GET'])
@login_required
def bulk_edit_ids():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return redirect(url_for('login'))
    
    quest_ids_str = request.args.get('quest_ids', '')
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    
    if not quest_ids_str:
        return redirect(url_for('manage_quests', title=title, level=level))
    
    quest_ids = [int(qid) for qid in quest_ids_str.split(',') if qid]
    quests = safe_query_all(Quest.query.filter(Quest.id.in_(quest_ids)).order_by(Quest.id))
    
    return render_template('bulk_edit_ids.html', quests=quests, title=title, level=level)

@app.route('/admin/quest/save_bulk_ids', methods=['POST'])
@login_required
def save_bulk_ids():
    if not current_user.is_admin():
        return redirect(url_for('login'))
    
    title = request.form.get('title', '')
    level = request.form.get('level', '')
    
    old_ids = request.form.getlist('old_id')
    new_ids_str = request.form.getlist('new_id')
    
    updates = []
    try:
        for old_id_str, new_id_str in zip(old_ids, new_ids_str):
            if not new_id_str: continue
            old_id = int(old_id_str)
            new_id = int(new_id_str)
            if old_id != new_id:
                updates.append((old_id, new_id))
    except ValueError:
        flash("IDは数値で入力してください。", "danger")
        return redirect(request.referrer)

    if not updates:
        flash("変更はありませんでした。", "info")
        return redirect(url_for('manage_quests', title=title, level=level))

    # Validate collisions
    new_id_set = set(u[1] for u in updates)
    if len(new_id_set) != len(updates):
        flash("新しいIDの間で重複があります。", "danger")
        return redirect(request.referrer)
    
    selected_old_ids = set(u[0] for u in updates)
    
    for _, new_id in updates:
        if new_id not in selected_old_ids:
            if safe_get(Quest, new_id):
                flash(f"エラー: ID {new_id} は既に他のクエストで使用されています。", "danger")
                return redirect(request.referrer)

    try:
        # Temporary offset strategy to avoid unique constraint violations during swap
        offset = 1000000
        
        # 1. Move to temporary range
        for old_id, new_id in updates:
            _update_quest_id_internal(old_id, old_id + offset)
        
        # 2. Move to final target IDs from temporary range
        for old_id, new_id in updates:
            _update_quest_id_internal(old_id + offset, new_id)
            
        safe_commit()
        db.session.expire_all()
        flash(f"{len(updates)}件のクエストIDを更新しました。", "success")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Bulk ID update error: {e}")
        flash(f"エラーが発生しました: {str(e)}", "danger")
        
    return redirect(url_for('manage_quests', title=title, level=level))

@app.route('/admin/quest/edit/<quest_id>', methods=['GET'])
@login_required
def edit_quest(quest_id):
    if not (current_user.is_admin() or current_user.is_teacher()):
        return redirect(url_for('login'))
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    if quest_id == 'new':
        quest = Quest(title=title, level=level, questname='') # Create a new quest object
    else:
        quest = safe_get(Quest, int(quest_id))
        if not quest:
            abort(404)
    # Fetch all unique titles and levels for dropdowns
    all_titles_raw = safe_query_all(db.session.query(Quest.title).distinct())
    all_titles_for_select = sorted([
        (SUBJECT_KEY_TO_JP.get(t[0], t[0]), t[0]) for t in all_titles_raw
    ], key=lambda x: x[0])

    all_levels = sorted(list(set([l[0] for l in safe_query_all(db.session.query(Quest.level).distinct())])))

    quest_display_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title) if quest and quest.title else ''

    return render_template('edit_quest.html', quest=quest, quest_id=quest_id, 
                           title=title, level=level, 
                           all_titles=all_titles_for_select, # New: (JP_title, EN_key) tuples
                           all_levels=all_levels,
                           quest_display_title=quest_display_title)

@app.route('/admin/quest/save/<quest_id>', methods=['POST'])
def save_quest(quest_id):
    title = request.form.get('title')
    level = request.form.get('level')
    questname = request.form.get('questname')
    new_id_str = request.form.get('new_id')

    # Level format validation: Lvn (n is a number)
    if not re.match(r'^Lv\d+$', level):
        flash("エラー: レベルは 'Lvn' (nは数字) の形式で入力してください (例: Lv1)。", "danger")
        return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

    try:
        if quest_id == 'new':
            if new_id_str:
                try:
                    new_id = int(new_id_str)
                    # Check if exists with retry logic
                    if safe_get(Quest, new_id):
                        flash(f"エラー: ID {new_id} は既に使用されています。", "danger")
                        return redirect(url_for('edit_quest', quest_id='new', title=title, level=level))
                    new_quest = Quest(id=new_id, title=title, level=level, questname=questname)
                except ValueError:
                    flash("エラー: IDは数値で入力してください。", "danger")
                    return redirect(url_for('edit_quest', quest_id='new', title=title, level=level))
            else:
                new_quest = Quest(title=title, level=level, questname=questname)
            
            db.session.add(new_quest)
            safe_commit()
            flash("新しいクエストを保存しました", "success")
            return redirect(url_for('edit_quest', quest_id=new_quest.id, title=title, level=level))
        else:
            old_id = int(quest_id)
            quest = safe_get(Quest, old_id)
            if not quest:
                flash("エラー: 更新対象のクエストが見つかりません。", "danger")
                return redirect(url_for('manage_quests'))
            
            # IDが変更された場合
            if new_id_str and int(new_id_str) != old_id:
                try:
                    new_id = int(new_id_str)
                    if safe_get(Quest, new_id):
                        flash(f"エラー: ID {new_id} は既に使用されています。", "danger")
                        return redirect(url_for('edit_quest', quest_id=old_id, title=title, level=level))
                    
                    # 共通のID更新ヘルパーを使用
                    _update_quest_id_internal(old_id, new_id)
                    
                    safe_commit()
                    db.session.expire_all()
                    quest = safe_get(Quest, new_id)
                    quest_id = str(new_id)
                except ValueError:
                    flash("エラー: IDは数値で入力してください。", "danger")
                    return redirect(url_for('edit_quest', quest_id=old_id, title=title, level=level))
                except Exception as e:
                    db.session.rollback()
                    flash(f"エラー: IDの更新に失敗しました。{str(e)}", "danger")
                    return redirect(url_for('edit_quest', quest_id=old_id, title=title, level=level))

            quest.title = title
            quest.level = level
            quest.questname = questname
            safe_commit()
            flash("クエスト情報を保存しました", "success")
            return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

    except OperationalError as e:
        if "disk I/O error" in str(e):
            app.logger.error(f"Critical Database Error during save_quest: {e}")
            flash('データベースの読み込み/書き込みエラーが発生しました。時間を置いてから再度「保存」を押してください。', 'error')
            return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))
        raise



@app.route('/admin/quest/renumber_questions/<int:quest_id>', methods=['POST'])
@login_required
def renumber_questions(quest_id):
    if not current_user.is_admin():
        return redirect(url_for('login'))

    title = request.form.get('title', '')
    level = request.form.get('level', '')
    ordered_ids = request.form.getlist('ordered_question_ids')

    if not ordered_ids:
        flash("並び替える問題がありません。", "warning")
        return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

    try:
        content_engine = db.get_engine(app, bind='content')
        # Step 1: Move all questions for this quest to a temporary ID range to avoid collisions
        # Temporary offset (e.g., 1,000,000)
        temp_offset = 1000000
        for qid in ordered_ids:
            db.session.execute(db.text("UPDATE questions SET id = id + :offset WHERE id = :old_id"),
                               {'offset': temp_offset, 'old_id': int(qid)},
                               bind_arguments={'bind': content_engine})

        # Step 2: Move back to the final ID based on the new order
        base_id = quest_id * 100
        for i, old_id in enumerate(ordered_ids):
            new_id = base_id + (i + 1)
            temp_id = int(old_id) + temp_offset
            db.session.execute(db.text("UPDATE questions SET id = :new_id WHERE id = :temp_id"),
                               {'new_id': new_id, 'temp_id': temp_id},
                               bind_arguments={'bind': content_engine})

        safe_commit()
        db.session.expire_all()
        flash(f"並び替えを保存し、問題IDを振り直しました（{base_id + 1}〜）。", "success")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Renumber questions error: {e}")
        flash(f"エラー: IDの振り直しに失敗しました。{str(e)}", "danger")

    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))
@app.route('/admin/question/edit/<int:quest_id>', methods=['POST'])
@login_required
def edit_question_action(quest_id):
    question_id = request.form.get('question_id')
    title = request.form.get('title', '')
    level = request.form.get('level', '')
    if question_id:
        return redirect(url_for('edit_question', quest_id=quest_id, question_id=question_id, title=title, level=level))
    flash("編集する問題を選択してください", "warning")
    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

@app.route('/admin/question/delete/<int:quest_id>', methods=['POST'])
@login_required
def delete_question_action(quest_id):
    question_id = request.form.get('question_id')
    title = request.form.get('title', '')
    level = request.form.get('level', '')
    if question_id:
        return redirect(url_for('delete_question', quest_id=quest_id, question_id=question_id, title=title, level=level))
    flash("削除する問題を選択してください", "warning")
    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

# Questionの削除
@app.route('/admin/question/delete/<int:quest_id>/<int:question_id>', methods=['GET','POST'])
@login_required
def delete_question(quest_id, question_id):
    if not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    question = safe_get(Question, question_id)
    if not question:
        abort(404)
    db.session.delete(question)
    safe_commit()
    flash("問題を削除しました", "success")
    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

# 新規Question作成画面
@app.route('/admin/question/add/<int:quest_id>')
@login_required
def add_question(quest_id):
    if not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)
    quest = safe_get(Quest, quest_id)
    if not quest:
        abort(404)
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    return render_template('edit_question.html', question=None, quest=quest, quest_id=quest_id, title=title, level=level, choices=[], answers=[])

# 問題の編集画面
@app.route('/admin/question/edit/<int:quest_id>/<question_id>', methods=['GET'])
@login_required
def edit_question(quest_id, question_id):
    if not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)
    quest = safe_get(Quest, quest_id)
    if not quest:
        abort(404)
    title = request.args.get('title', '')
    level = request.args.get('level', '')

    if question_id == 'new':
        return render_template('edit_question.html', quest_id=quest.id, question=None, title=title, level=level)
    else:
        question = safe_get(Question, int(question_id))
        if not question:
            abort(404)
        choices = None
        answers = None
        if question.type == 'choice' or question.type == 'multiple_choice':
            choices = json.loads(question.choices) if question.choices else None
        elif question.type == 'svg_interactive' or question.type == 'figure_choice':
            # 1. Extract SVG for the textarea
            try:
                choices_data = json.loads(question.choices)
                if isinstance(choices_data, dict) and 'svg' in choices_data:
                    choices = choices_data['svg']
                else:
                    choices = question.choices
            except (json.JSONDecodeError, TypeError):
                choices = question.choices
            
            # 2. Load sub-questions into answers
            try:
                answers = json.loads(question.answer) if question.answer else []
            except json.JSONDecodeError:
                answers = []
        elif question.type == 'numeric':
            try:
                answers = json.loads(question.answer) if question.answer else []
            except json.JSONDecodeError:
                answers = []
        elif question.type == 'function_graph' and question.answer:
            # NEW: Load sub-questions from the 'choices' field
            try:
                answers = json.loads(question.choices) if question.choices else []
            except json.JSONDecodeError:
                answers = []
        elif question.type == 'function_graph_choice':
            # Graph definitions are stored in question.choices (database field)
            try:
                choices = json.loads(question.choices) if question.choices else [] # This is correct for graph definitions
            except json.JSONDecodeError:
                choices = []
            
            # Sub-questions (prompts, choices, answer) are stored in question.answer (database field)
            try:
                answers = json.loads(question.answer) if question.answer else [] # This should be the list of sub-questions
            except json.JSONDecodeError:
                answers = []
        elif question.type == 'english_reading':
            try:
                word_list_data = json.loads(question.choices) if question.choices else {'word_list': []}
                choices = word_list_data.get('word_list', [])
            except Exception:
                choices = []
            
            try:
                answers = json.loads(question.answer) if question.answer else []
            except Exception:
                answers = []


        # question.answers にセット（テンプレートで読みやすくする）
        if answers is not None:
            question.answers = answers

        # Debug log for sort type answer
        if question.type == 'sort':
            app.logger.debug(f"Edit Question (sort): question.answer = '{question.answer}'")

        return render_template('edit_question.html', quest_id=quest.id, question=question, choices=choices, answers=answers, title=title, level=level)

# 問題の保存画面
@app.route('/admin/question/save/<int:quest_id>', methods=['POST'])
@login_required
def save_question(quest_id):
    if not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)
    try:
        question_id = request.values.get('question_id')
        title = request.form.get('title', '')
        level = request.form.get('level', '')

        q_type = request.form['type']
        text = request.form['text']
        if question_id == 'new':
            # クエストIDに基づいた自動採番 (QuestID * 100 + 連番)
            base_id = quest_id * 100
            existing_ids = [q.id for q in safe_query_all(Question.query.filter(Question.id > base_id, Question.id < base_id + 100))]
            if existing_ids:
                new_q_id = max(existing_ids) + 1
            else:
                new_q_id = base_id + 1
            
            question = Question(id=new_q_id, quest_id=quest_id, type=q_type, text=text)
        else:
            question = safe_get(Question, int(question_id))
            if not question:
                abort(404)
            question.type = q_type
            question.text = text
        question.explanation = request.form.get('explanation', '').strip()

        if q_type == 'choice' or q_type == 'multiple_choice':
            choices = [request.form.get(f'choice{i}', '') for i in range(4)]
            answer = request.form['answer']
            question.choices = json.dumps(choices)
            question.answer = answer

        elif q_type == 'sort':
            question.choices = None
            question.answer = request.form.get('answer_sort', '')

        elif q_type == 'fill_in_the_blank_en':
            question.choices = None
            question.answer = request.form['answer_fill_in_the_blank_en']

        elif q_type == 'numeric':
            answers = []
            for i in range(4):
                label = request.form.get(f'label{i}', '')
                value_str = request.form.get(f'num_answer{i}', '')
                if label and value_str:
                    try:
                        # Ensure value is a valid number before converting
                        answers.append({'label': label, 'answer': int(value_str)})
                    except (ValueError, TypeError):
                        # Skip invalid entries gracefully
                        flash(f'数値入力の解答「{value_str}」は無効なため、スキップされました。', 'warning')
                        pass
            question.choices = None
            question.answer = json.dumps(answers)

        elif q_type == 'svg_interactive':
            svg_content = request.form.get('svg_content', '')
            ggb_data = request.form.get('ggb_data', '')
            svg_width = request.form.get('svg_width', '')
            svg_height = request.form.get('svg_height', '')
            sub_ids = request.form.getlist('sub_id')
            sub_prompts = request.form.getlist('sub_prompt')
            sub_answers = request.form.getlist('sub_answer')

            sub_questions = []
            # Use the length of sub_prompts as the base to avoid issues if other lists are shorter
            for i in range(len(sub_prompts)):
                prompt = sub_prompts[i].strip()
                if prompt: # Save if there is at least a prompt
                    sub_questions.append({
                        'id': sub_ids[i] if i < len(sub_ids) else f'new_{int(time.time()*1000)}_{i}',
                        'prompt': prompt,
                        'answer': sub_answers[i] if i < len(sub_answers) else ''
                    })

            # Store SVG, GGB, and size data as JSON in choices
            question.choices = json.dumps({
                'svg': svg_content, 
                'ggb': ggb_data,
                'width': svg_width,
                'height': svg_height
            })
            question.answer = json.dumps(sub_questions)

        elif q_type == 'figure_choice':
            svg_content = request.form.get('figure_choice_svg_content', '')
            ggb_data = request.form.get('figure_choice_ggb_data', '')
            svg_width = request.form.get('figure_choice_svg_width', '')
            svg_height = request.form.get('figure_choice_svg_height', '')
            sub_ids = request.form.getlist('figure_choice_sub_id')
            sub_prompts = request.form.getlist('figure_choice_sub_prompt')
            sub_answers = request.form.getlist('figure_choice_sub_answer')

            sub_questions = []
            for i in range(len(sub_prompts)):
                prompt = sub_prompts[i].strip()
                if prompt:
                    choices = [request.form.get(f'figure_choice_sub_choice_{i}_{j}', '') for j in range(4)]
                    sub_questions.append({
                        'id': sub_ids[i] if i < len(sub_ids) else f'new_{int(time.time()*1000)}_{i}',
                        'prompt': prompt,
                        'choices': choices,
                        'answer': sub_answers[i] if i < len(sub_answers) else ''
                    })
            
            # Store SVG, GGB, and size data as JSON in choices
            question.choices = json.dumps({
                'svg': svg_content, 
                'ggb': ggb_data,
                'width': svg_width,
                'height': svg_height
            })
            question.answer = json.dumps(sub_questions)

        elif q_type == 'function_graph':
            # The 'answer' field stores the function definitions for the graph
            graph_definitions_json = request.form.get('answer_function_graph', '[]')
            width = request.form.get('function_graph_width', '')
            height = request.form.get('function_graph_height', '')
            try:
                definitions = json.loads(graph_definitions_json)
                # Store width/height in the answer JSON
                question.answer = json.dumps({
                    'definitions': definitions,
                    'width': width,
                    'height': height
                })
            except json.JSONDecodeError:
                question.answer = '[]'
                flash('方程式グラフの定義データ形式が無効だったため、保存されませんでした。', 'error')

            # The 'choices' field stores the sub-questions (prompts and answers)
            sub_questions_json = request.form.get('answers', '[]')
            try:
                json.loads(sub_questions_json)
                question.choices = sub_questions_json
            except json.JSONDecodeError:
                question.choices = '[]'
                flash('方程式グラフの回答データ形式が無効だったため、保存されませんでした。', 'error')

        elif q_type == 'function_graph_choice':
            # Graph definitions are stored in question.choices
            graph_definitions_json = request.form.get('function_graph_choice_definitions', '[]')
            width = request.form.get('function_graph_choice_width', '')
            height = request.form.get('function_graph_choice_height', '')
            try:
                # フォームから受け取った JSON 文字列をパースする
                data = json.loads(graph_definitions_json)
                
                # 構造を整理して保存 (definitionsリスト, 幅, 高さ)
                # dataがすでに入力データ構造であれば、definitionsプロパティから取得する
                definitions = data.get('definitions', data)
                
                question.choices = json.dumps({
                    'definitions': definitions,
                    'width': width,
                    'height': height
                })
            except json.JSONDecodeError:
                question.choices = '[]'
                flash('方程式グラフ（選択）のグラフ定義データ形式が無効だったため、保存されませんでした。', 'error')

            # Sub-questions are stored in question.answer
            # (assuming sub-questions parsing logic exists further down in save_question)
            sub_prompts = request.form.getlist('fgc_sub_prompt')
            sub_answers = request.form.getlist('fgc_sub_answer')
            sub_questions = []
            for i in range(len(sub_prompts)):
                if sub_prompts[i]:
                    choices = [request.form.get(f'fgc_sub_choice_{i}_{j}', '') for j in range(4)]
                    sub_questions.append({
                        'prompt': sub_prompts[i],
                        'choices': choices,
                        'answer': sub_answers[i] if i < len(sub_answers) else ''
                    })
            question.answer = json.dumps(sub_questions)
        elif q_type == 'english_reading':
            table_text = request.form.get('reading_words_table', '')
            word_list = []
            for line in table_text.splitlines():
                line = line.strip()
                if not line.startswith('|') or not line.endswith('|'):
                    continue
                parts = [p.strip() for p in line[1:-1].split('|')]
                if len(parts) < 2:
                    continue
                word = parts[0]
                meaning = parts[1]
                if word == '単語' or word == 'word' or all(c in '-: ' for c in word) or not word:
                    continue
                word_list.append({
                    'word': word,
                    'meaning': meaning
                })
            question.choices = json.dumps({'word_list': word_list})

            sub_ids = request.form.getlist('reading_sub_id')
            sub_prompts = request.form.getlist('reading_sub_prompt')
            sub_answers = request.form.getlist('reading_sub_answer')

            sub_questions = []
            for i in range(len(sub_prompts)):
                prompt = sub_prompts[i].strip()
                if prompt:
                    choices = [request.form.get(f'reading_sub_choice_{i}_{j}', '') for j in range(4)]
                    sub_questions.append({
                        'id': sub_ids[i] if i < len(sub_ids) else f'new_{int(time.time()*1000)}_{i}',
                        'prompt': prompt,
                        'choices': choices,
                        'answer': sub_answers[i] if i < len(sub_answers) else ''
                    })
            question.answer = json.dumps(sub_questions)
        if question_id == 'new':
            db.session.add(question)
        
        safe_commit()
        flash('問題を保存しました', 'success')

    except OperationalError as e:
        if "disk I/O error" in str(e):
            app.logger.error(f"Critical Database Error: {e}")
            flash('データベースの書き込みエラーが発生しました。しばらく時間を置いてから再度お試しください。', 'error')
        else:
            raise

    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

@app.route('/preview_question', methods=['POST'])
@login_required
def preview_question():
    """ 問題編集画面からのPOSTデータを受け取り、プレビューを表示する """
    q_type = request.form.get('type')
    text = request.form.get('text', '')
    explanation = request.form.get('explanation', '')
    
    question_data = {
        'type': q_type,
        'text': text,
        'explanation': explanation,
        'choices': None,
        'answer': None,
        'answers': None,
        'svg_content': None,
        'sub_questions': None
    }

    if q_type == 'choice' or q_type == 'multiple_choice':
        question_data['choices'] = [request.form.get(f'choice{i}', '') for i in range(4)]
        question_data['answer'] = request.form.get('answer', '')
    
    elif q_type == 'sort':
        question_data['answer'] = request.form.get('answer_sort', '')
        # For sorting questions, the choices are generated from the answer
        answer_text = question_data['answer']
        if answer_text:
            # A simple shuffle of characters or words can be done here if needed.
            # For preview, we can just show the elements that will be sorted.
            question_data['choices'] = sorted(answer_text.split(' '), key=lambda k: random.random())


    elif q_type == 'fill_in_the_blank_en':
        question_data['answer'] = request.form.get('answer_fill_in_the_blank_en', '')

    elif q_type == 'numeric':
        answers = []
        for i in range(4):
            label = request.form.get(f'label{i}', '')
            value_str = request.form.get(f'num_answer{i}', '')
            if label: # label or value might be present
                answers.append({'label': label, 'answer': value_str})
        question_data['answers'] = answers

    elif q_type == 'svg_interactive':
        question_data['svg_content'] = request.form.get('svg_content', '')
        # Pass GGB data as well for preview state if needed, though not strictly required for static preview
        question_data['choices'] = json.dumps({
            'svg': question_data['svg_content'], 
            'ggb': request.form.get('ggb_data', ''),
            'width': request.form.get('svg_width', ''),
            'height': request.form.get('svg_height', '')
        })
        sub_ids = request.form.getlist('sub_id')
        sub_prompts = request.form.getlist('sub_prompt')
        sub_answers = request.form.getlist('sub_answer')
        
        sub_questions = []
        for i in range(len(sub_ids)):
            if sub_prompts[i]:
                sub_questions.append({
                    'id': sub_ids[i],
                    'prompt': sub_prompts[i],
                    'answer': sub_answers[i]
                })
        question_data['sub_questions'] = sub_questions
        question_data['answer'] = sub_questions

    elif q_type == 'figure_choice':
        question_data['svg_content'] = request.form.get('figure_choice_svg_content', '')
        question_data['choices'] = json.dumps({
            'svg': question_data['svg_content'], 
            'ggb': request.form.get('figure_choice_ggb_data', ''),
            'width': request.form.get('figure_choice_svg_width', ''),
            'height': request.form.get('figure_choice_svg_height', '')
        })
        sub_ids = request.form.getlist('figure_choice_sub_id')
        sub_prompts = request.form.getlist('figure_choice_sub_prompt')
        sub_answers = request.form.getlist('figure_choice_sub_answer')
        
        sub_questions = []
        for i in range(len(sub_prompts)):
            if sub_prompts[i]:
                choices = [request.form.get(f'figure_choice_sub_choice_{i}_{j}', '') for j in range(4)]
                sub_questions.append({
                    'id': sub_ids[i] if i < len(sub_ids) else f'new{i}',
                    'prompt': sub_prompts[i],
                    'choices': choices,
                    'answer': sub_answers[i] if i < len(sub_answers) else ''
                })
        question_data['sub_questions'] = sub_questions
        question_data['answer'] = sub_questions

    elif q_type == 'function_graph':
        # Get graph definitions (definitions + width + height)
        graph_json_string = request.form.get('answer_function_graph', '[]')
        try:
            # We want the whole object {definitions, width, height}
            question_data['answer'] = json.loads(graph_json_string)
        except json.JSONDecodeError:
            question_data['answer'] = []
        
        # Get sub-questions (prompts and answers)
        answers_json_string = request.form.get('answers', '[]')
        try:
            # Put sub-questions into 'choices' to align with how quest_run handles it
            question_data['choices'] = json.loads(answers_json_string)
        except json.JSONDecodeError:
            question_data['choices'] = []

    elif q_type == 'function_graph_choice':
        # Get graph definitions (definitions + width + height)
        graph_json_string = request.form.get('function_graph_choice_definitions', '[]')
        try:
            question_data['graph_data'] = json.loads(graph_json_string)
        except json.JSONDecodeError:
            question_data['graph_data'] = []
        
        # Get sub-questions (prompts, choices, answers)
        sub_prompts = request.form.getlist('fgc_sub_prompt')
        sub_answers = request.form.getlist('fgc_sub_answer')
        
        sub_questions_list = []
        for i in range(len(sub_prompts)):
            if sub_prompts[i]:
                choices_for_sub_q = [request.form.get(f'fgc_sub_choice_{i}_{j}', '') for j in range(4)]
                sub_questions_list.append({
                    'id': f'new{i}', # Assign a temporary ID for preview
                    'prompt': sub_prompts[i],
                    'choices': choices_for_sub_q,
                    'answer': sub_answers[i] if i < len(sub_answers) else ''
                })
        question_data['sub_questions'] = sub_questions_list
        question_data['correct_answer_text'] = None

    elif q_type == 'english_reading':
        table_text = request.form.get('reading_words_table', '')
        word_list = []
        for line in table_text.splitlines():
            line = line.strip()
            if not line.startswith('|') or not line.endswith('|'):
                continue
            parts = [p.strip() for p in line[1:-1].split('|')]
            if len(parts) < 2:
                continue
            word = parts[0]
            meaning = parts[1]
            if word == '単語' or word == 'word' or all(c in '-: ' for c in word) or not word:
                continue
            word_list.append({
                'word': word,
                'meaning': meaning
            })
        question_data['word_list'] = word_list
        question_data['choices'] = json.dumps({'word_list': word_list})

        sub_ids = request.form.getlist('reading_sub_id')
        sub_prompts = request.form.getlist('reading_sub_prompt')
        sub_answers = request.form.getlist('reading_sub_answer')

        sub_questions = []
        for i in range(len(sub_prompts)):
            prompt = sub_prompts[i].strip()
            if prompt:
                choices = [request.form.get(f'reading_sub_choice_{i}_{j}', '') for j in range(4)]
                sub_questions.append({
                    'id': sub_ids[i] if i < len(sub_ids) else f'new{i}',
                    'prompt': prompt,
                    'choices': choices,
                    'answer': sub_answers[i] if i < len(sub_answers) else ''
                })
        question_data['sub_questions'] = sub_questions
        question_data['answer'] = json.dumps(sub_questions)

    return render_template('question_preview.html', question=question_data)


# タイトル一覧表示（ステップ1）
@app.route('/select_title_admin')
@login_required
def select_title_admin():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return redirect(url_for(f"dashboard_{current_user.role}"))
    titles = safe_query_all(db.session.query(Quest.title).distinct())
    jp_titles = [SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in titles]
    return render_template('select_title_admin.html', titles=jp_titles)


# レベル選択（ステップ2）
@app.route('/select_level_admin/<title>')
@login_required
def select_level_admin(title):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    levels = safe_query_all(db.session.query(Quest.level).filter_by(title=title_key).distinct())
    return render_template('select_level_admin.html', title=title, levels=[l[0] for l in levels])

@app.route('/select_quest_admin/<title>/<level>')
@login_required
def select_quest_by_title_level_admin(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = safe_query_all(Quest.query.filter_by(title=title_key, level=level))
    print(quests)
    return render_template(
        'select_quest_admin.html',
        title=title,
        level=level,
        quests=quests
    )

@app.route('/group_learning/<int:quest_id>')
@login_required
def quest_run_group(quest_id):
    quest = safe_get(Quest, quest_id)
    if not quest:
        return "指定されたクエストが存在しません", 404

    # すべての同タイトルの問題を取得（1問＝1レコード）
    quest = safe_query_first(Quest.query.filter_by(id=quest_id))  # ✅ 1件의 Questオブジェクトになる
    if not quest:
        return "クエストが見つかりません", 404

    all_questions = quest.questions  # Question オブジェクトのリスト

    questions = []

    for q in all_questions:
        choices = None
        if q.type == 'choice':
            # q.choicesが文字列のJSONならパースする
            try:
                choices = json.loads(q.choices)
                random.shuffle(choices)  # 選択肢をシャッフル
            except Exception:
                choices = q.choices  # パースできなければそのまま
        else:
            try:
                choices = json.loads(q.choices)
            except Exception:
                choices = q.choices

        # q.answerが文字列のJSONならパースする
        try:
            answer = json.loads(q.answer)
        except Exception:
            answer = q.answer  # パースできなければそのまま

        # すでに構造化されていないので、自前で構築
        if q.type == 'svg_interactive' or q.type == 'figure_choice':
            # Try to parse choices as JSON (new format with 'svg' and 'ggb')
            svg_display = q.choices
            try:
                choices_json = json.loads(q.choices)
                if isinstance(choices_json, dict) and 'svg' in choices_json:
                    svg_display = choices_json['svg']
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                sub_questions = json.loads(q.answer) if q.answer else []
                # figure_choice の場合は各小問の選択肢をシャッフル
                if q.type == 'figure_choice':
                    for sub_q in sub_questions:
                        if 'choices' in sub_q and isinstance(sub_q['choices'], list):
                            random.shuffle(sub_q['choices'])
            except json.JSONDecodeError:
                sub_questions = []

            questions.append({
                "type": q.type,
                "text": q.text,
                "choices": q.choices, # Pass raw JSON for size extraction in template
                "svg_content": svg_display,
                "sub_questions": sub_questions,
                "explanation": q.explanation
            })
        elif q.type == 'function_graph':
            questions.append({
                "type": q.type,
                "text": q.text,
                "answer": answer, # This will be the parsed list of dicts
                "choices": choices,
                "answers": None,
                "explanation": q.explanation
            })
        elif q.type == 'function_graph_choice':
            # q.choices is graph_data, q.answer is sub_questions
            try:
                graph_data = json.loads(q.choices) if q.choices else []
            except json.JSONDecodeError:
                graph_data = []

            try:
                sub_questions = json.loads(q.answer) if q.answer else []
                # 各小問の選択肢をシャッフル
                for sub_q in sub_questions:
                    if 'choices' in sub_q and isinstance(sub_q['choices'], list):
                        random.shuffle(sub_q['choices'])
            except json.JSONDecodeError:
                sub_questions = []

            questions.append({
                "type": q.type,
                "text": q.text,
                "graph_data": graph_data,
                "sub_questions": sub_questions,
                "explanation": q.explanation
            })
        else:
            questions.append({
                "type": q.type,  
                "text": q.text,
                "choices": choices,
                "answer": answer if q.type != "numeric" else None,
                "answers": answer if q.type == "numeric" else None,
                "explanation": q.explanation
            })

    jp_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title)
    return render_template("group_learning.html", quest_id=quest_id, quest=quest, title=jp_title, level=quest.level, questions=questions)

@app.route("/parent/students")
@login_required
def parent_students():
    if not current_user.is_parent():
        return redirect(url_for("dashboard"))

    parent_id = current_user.id
    children = safe_query_all(User.query.filter_by(parent_id=parent_id, role="student"))

    student_data = []
    for child in children:
        histories = safe_query_all(QuestHistory.query.filter_by(user_id=child.id))
        total_medals = sum(h.attempts for h in histories)
        student_data.append({
            "student": child,
            "histories": histories,
            "medal_count": total_medals
        })

    return render_template("parent_students.html", student_data=student_data)

@app.route('/admin/questions/import', methods=['GET'])
@login_required
def import_questions_gui():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return redirect(url_for('login'))
    # 過去のフラッシュメッセージをすべて消費（破棄）して、再読み込み時に表示されないようにする
    get_flashed_messages()
    return render_template('import_questions.html')

@app.route('/admin/questions/import', methods=['POST'])
@login_required
def import_questions_action():
    if not (current_user.is_admin() or current_user.is_teacher()):
        abort(403)
    
    file = request.files.get('file')
    if not file or file.filename == '':
        flash("JSONファイルを選択してください", "danger")
        return redirect(url_for('import_questions_gui'))
    
    try:
        filename = file.filename.lower()
        if not filename.endswith('.json'):
            flash("サポートされていないファイル形式です (.json を使用してください)", "danger")
            return redirect(url_for('import_questions_gui'))

        raw_data = json.loads(file.read().decode('utf-8'))
        
        # --- Normalization ---
        normalized_quests = []
        normalized_questions = []
        
        # Context and counters for normalization
        context = {'last_quest_id': None}
        temp_id_counter = 0

        def process_entry(row, inherited_quest_id=None):
            nonlocal temp_id_counter
            # Detect type
            rec_type = row.get('record_type')
            if not rec_type:
                if 'questname' in row or 'subject' in row:
                    rec_type = 'quest'
                elif 'text' in row and 'type' in row:
                    rec_type = 'question'
                elif 'questions' in row and isinstance(row['questions'], list):
                    rec_type = 'quest'
            
            if rec_type == 'quest':
                q_id = row.get('id')
                # Assign a temporary ID if no ID is present, to link nested questions
                if not q_id:
                    temp_id_counter += 1
                    q_id = f"_temp_quest_{temp_id_counter}"
                
                context['last_quest_id'] = q_id
                
                quest_data = {
                    'id': q_id,
                    'title': row.get('title') or row.get('subject'),
                    'level': row.get('level'),
                    'questname': row.get('questname'),
                    'world_name': row.get('world_name')
                }
                normalized_quests.append(quest_data)

                # Process nested questions
                if 'questions' in row and isinstance(row['questions'], list):
                    for q_row in row['questions']:
                        process_entry(q_row, inherited_quest_id=q_id)
            
            elif rec_type == 'question':
                # Link to quest: explicit > inherited > flat list context
                quest_id = row.get('quest_id') or row.get('questId') or row.get('quest') or inherited_quest_id or context['last_quest_id']
                
                q_data = {
                    'id': row.get('id'),
                    'quest_id': quest_id,
                    'type': row.get('type'),
                    'text': row.get('text'),
                    'explanation': row.get('explanation'),
                    'choices': row.get('choices'),
                    'answer': row.get('answer')
                }
                # Flexible mapping for special types and field names
                if q_data['type'] == 'numeric' and 'answers' in row:
                    q_data['answer'] = row['answers']
                elif q_data['type'] == 'svg_interactive' or q_data['type'] == 'figure_choice':
                    if 'svg_content' in row:
                        q_data['choices'] = row['svg_content']
                    if 'sub_questions' in row:
                        q_data['answer'] = row['sub_questions']
                
                normalized_questions.append(q_data)

        if isinstance(raw_data, dict):
            # Handle quests.json format: { "101": { ... }, "102": { ... } }
            for key, val in raw_data.items():
                if isinstance(val, dict):
                    if 'id' not in val:
                        try:
                            val['id'] = int(key)
                        except ValueError:
                            # Keep as string (e.g. "q101")
                            val['id'] = key
                    process_entry(val)
        elif isinstance(raw_data, list):
            for entry in raw_data:
                process_entry(entry)
        
        app.logger.debug(f"Normalized: {len(normalized_quests)} quests, {len(normalized_questions)} questions")

        # --- Phase 1: Process Quests ---
        updated_quest_count = 0
        inserted_quest_count = 0
        quest_id_map = {} # Identifier (from JSON) to real DB ID
        quest_name_map = {} # questname to real DB ID

        for q_row in normalized_quests:
            qid_json = q_row.get('id')
            title_raw = q_row.get('title', 'misc')
            title = SUBJECT_JP_TO_KEY.get(title_raw, title_raw)
            level = q_row.get('level', 'Lv1')
            questname = q_row.get('questname', f'Imported Quest' if not qid_json else f'Quest {qid_json}')
            world_name = q_row.get('world_name', 'fantasy')

            quest = None
            # 1. Try by ID
            if qid_json:
                try:
                    quest = safe_get(Quest, int(qid_json))
                except (ValueError, TypeError):
                    pass
            
            # 2. Try by questname + title + level if still not found
            if not quest and questname:
                quest = safe_query_first(Quest.query.filter_by(questname=questname, title=title, level=level))
            
            if quest:
                quest.title = title
                quest.level = level
                quest.questname = questname
                if world_name: quest.world_name = world_name
                updated_quest_count += 1
                assigned_id = quest.id
            else:
                new_quest = Quest(
                    title=title,
                    level=level,
                    questname=questname,
                    world_name=world_name
                )
                # Only set explicit ID if it's a numeric ID from JSON
                if qid_json:
                    try:
                        new_quest.id = int(qid_json)
                    except (ValueError, TypeError):
                        pass
                
                db.session.add(new_quest)
                db.session.flush()
                inserted_quest_count += 1
                assigned_id = new_quest.id
            
            if qid_json:
                quest_id_map[str(qid_json)] = assigned_id
            if questname:
                quest_name_map[questname] = assigned_id
        
        # --- Phase 2: Process Questions ---
        updated_q_count = 0
        inserted_q_count = 0
        
        for row in normalized_questions:
            q_id_raw = row.get('id')
            raw_quest_id = row.get('quest_id')
            
            # Resolve quest_id
            quest_id = None
            if raw_quest_id:
                # Try identifier map first
                quest_id = quest_id_map.get(str(raw_quest_id))
                if not quest_id:
                    # Try direct cast
                    try:
                        quest_id = int(raw_quest_id)
                    except (ValueError, TypeError):
                        pass
            
            if not quest_id:
                # Last resort: if this question record also has a questname (redundant but helpful)
                q_questname = row.get('questname')
                if q_questname:
                    quest_id = quest_name_map.get(q_questname)
            
            if quest_id:
                quest_id = int(quest_id)
            else:
                app.logger.debug(f"Skipping question (unresolved quest_id): {row.get('text', '')[:20]}")
                continue

            q_type = row.get('type')
            text = row.get('text')
            choices = row.get('choices')
            answer = row.get('answer')
            explanation = row.get('explanation')
            
            if not q_type or not text: continue

            if choices is not None and not isinstance(choices, str):
                choices = json.dumps(choices, ensure_ascii=False)
            if answer is not None and not isinstance(answer, str):
                answer = json.dumps(answer, ensure_ascii=False)

            question = None
            if q_id_raw:
                try:
                    question = safe_get(Question, int(q_id_raw))
                except (ValueError, TypeError):
                    pass
            
            if question:
                question.quest_id = quest_id
                question.type = q_type
                question.text = text
                question.choices = choices if choices and str(choices).strip() != '' else None
                question.answer = answer
                question.explanation = explanation
                updated_q_count += 1
            else:
                new_q = Question(
                    quest_id=quest_id, type=q_type, text=text,
                    choices=choices if choices and str(choices).strip() != '' else None,
                    answer=answer, explanation=explanation
                )
                if q_id_raw:
                    try:
                        new_q.id = int(q_id_raw)
                    except (ValueError, TypeError):
                        pass
                
                if not new_q.id:
                    # Auto-assign Question ID (QuestID * 100 + next serial)
                    base_id = quest_id * 100
                    max_q_id = db.session.query(func.max(Question.id)).filter(Question.id > base_id, Question.id < base_id + 100).scalar()
                    new_q.id = (max_q_id + 1) if max_q_id else (base_id + 1)
                
                db.session.add(new_q)
                inserted_q_count += 1
                db.session.flush()

        safe_commit()
        list_url = url_for('manage_quests')
        flash(f'インポート完了: クエスト(更新{updated_quest_count}/新規{inserted_quest_count}), 問題(更新{updated_q_count}/新規{inserted_q_count})。 <a href="{list_url}">クエスト一覧で確認する</a>', "success")
    except IntegrityError as ie:
        db.session.rollback()
        msg = str(ie)
        if "FOREIGN KEY" in msg:
            flash("インポートエラー: 指定された クエストID が存在しません。先に「問題の追加」からクエストを作成してください。", "danger")
        else:
            flash(f"データベース整合性エラー: {msg}", "danger")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Import error: {e}")
        flash(f"インポートエラー: {str(e)}", "danger")
        
    return redirect(url_for('import_questions_gui'))

if __name__ == '__main__':
    app.logger.setLevel(logging.DEBUG)  # ログレベルをDEBUGに設定
    app.run(debug=True)



# from pyngrok import ngrok, conf
# from getpass import getpass
# conf.get_default().auth_token = getpass('Authtokenを貼り付けてEnterキーを押して下さい ')

# if __name__ == "__main__":
# # ngrokトークンを設定
#     # ngrokでFlaskアプリを公開
#     public_url = ngrok.connect(5000)
#     print(f"ngrok URL: {public_url}")

#     app.run(host="127.0.0.1", port=5000, debug=False) # Flaskサーバを起動
