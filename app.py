from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, case
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from models import QuestHistory, Quest, Question, QuestAttemptLog
import json
import logging
import random
from utils.svg_preview_bp import bp as svg_preview_bp # Import the blueprint

# 科目キーと日本語名のマッピング
SUBJECT_KEY_TO_JP = {
    'math': '数学',
    'english': '英語',
    'japanese': '国語'
}
# 日本語名から英語キーへの逆引きマップ
SUBJECT_JP_TO_KEY = {v: k for k, v in SUBJECT_KEY_TO_JP.items()}

from models import db, User, Quest, UserProgress

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # セッション管理に必要

# データベース設定（例: SQLite）
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mquest.db?charset=utf8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DBとLoginManagerの初期化
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.register_blueprint(svg_preview_bp) # Register the blueprint

@app.route('/')
def home():
    return redirect(url_for('login'))

# ユーザーロード用コールバック
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ユーザーログイン処理
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

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
        db.session.commit()
        
        return redirect(url_for(f"dashboard_{current_user.role}"))

    return render_template('change_password.html')  # パスワード変更フォームを表示


# ログアウト処理
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 初回のユーザー作成（ロール付き）
@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        if role not in ['admin', 'student', 'parent']:
            return '無効なロールです'

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
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

    # ▼ 世界制覇機能：制覇済みのクエストとその挑戦回数、マップタイプを取得
    
    # 1. ユーザーがクリアしたクエストの進捗情報を取得
    progress_records = UserProgress.query.filter_by(user_id=current_user.id, status='cleared').all()
    cleared_quest_ids = [p.quest_id for p in progress_records]

    if not cleared_quest_ids:
        conquered_quest_data = []
    else:
        # 2. クリアしたクエストの詳細情報（world_nameを含む）を取得
        cleared_quests_details = Quest.query.filter(Quest.id.in_(cleared_quest_ids)).all()
        quest_map = {q.id: q for q in cleared_quests_details}

        # 3. ユーザーの全クエスト挑戦履歴を取得
        histories = QuestHistory.query.filter_by(user_id=current_user.id).all()
        attempts_map = {h.quest_id: h.attempts for h in histories}

        # 4. フロントエンドに渡すための最終的なデータ構造を構築
        conquered_quest_data = []
        for quest_id in cleared_quest_ids:
            quest_detail = quest_map.get(quest_id)
            if quest_detail:
                conquered_quest_data.append({
                    "quest_id": quest_id,
                    "attempts": attempts_map.get(quest_id, 0),
                    "map_type": quest_detail.world_name 
                })

    return render_template(
        'dashboard_student.html',
        user_id=current_user.id, 
        conquered_quest_data=conquered_quest_data # 新しいデータをテンプレートに渡す
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

# タイトル一覧表示（ステップ1）
@app.route('/select_title')
@login_required
def select_title():
    titles = db.session.query(Quest.title).distinct().all()
    # ユーザーに表示する際は、ここで日本語に変換
    jp_titles = [SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in titles]
    return render_template('select_title.html', titles=jp_titles)

# レベル選択（ステップ2）
@app.route('/select_level/<title>')
@login_required
def select_level(title):
    print(f"Title: {title}")
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    levels = db.session.query(Quest.level).filter_by(title=title_key).distinct().all()
    print(f"Levels: {levels}")
    return render_template('select_level.html', title=title, levels=[l[0] for l in levels])

@app.route('/select_quest/<title>/<level>')
@login_required
def select_quest_by_title_level(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = Quest.query.filter_by(title=title_key, level=level).all()

    history_map = {}
    if current_user.is_authenticated:
        user_id = current_user.id
        histories = QuestHistory.query.filter(
            QuestHistory.user_id == user_id,
            QuestHistory.quest_id.in_([q.id for q in quests])
        ).all()
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

    quest = Quest.get(quest_id)
    if not quest:
        return "クエストが見つかりません", 404

    if request.method == 'POST':
        # 解答取得と採点
        submitted = [int(request.form.get(f'q{i}')) for i in range(len(quest['questions']))]
        correct = [q['answer'] for q in quest['questions']]
        score = sum([1 for i, ans in enumerate(submitted) if ans == correct[i]])

        # 結果表示へ
        return render_template(
            'quest_result.html',
            score=score,
            total=len(correct),
            cleared=(score == len(correct)),
            quest_id=quest_id
        )

    return render_template('quest_run.html', quest=quest, quest_id=quest_id)

@app.route("/quest/select/<title>/<level>")
def select_quest(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = Quest.query.filter_by(title=title_key, level=level).all()
    print(quests)
    return render_template(
        'select_quest.html',
        title=title,
        level=level,
        quests=quests
    )

@app.route("/quest/run/<int:quest_id>")
def quest_run(quest_id):
    quest = db.session.get(Quest, quest_id)
    if not quest:
        return "指定されたクエストが存在しません", 404

    # すべての同タイトルの問題を取得（1問＝1レコード）
    quest = Quest.query.filter_by(id=quest_id).first()  # ✅ 1件のQuestオブジェクトになる
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
        if q.type == 'svg_interactive':
            questions.append({
                "type": q.type,
                "text": q.text,
                "svg_content": q.choices, # choicesにSVGコンテンツを格納
                "sub_questions": json.loads(q.answer) # answerにサブ問題を格納
            })
        elif q.type == 'function_graph':
            questions.append({
                "type": q.type,
                "text": q.text,
                "answer": answer, # This will be the parsed list of dicts
                "choices": choices,
                "answers": None
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
        quest = db.session.get(Quest, quest_id)
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
                    expected_val = str(sub_q['answer'])
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
                    expected_val = str(ans['answer'])
                    expected.append({ans['label']: expected_val})
                    user_input.append({ans['label']: user_val})
                    if user_val != expected_val:
                        correct = False
                user_answer = user_input

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
                history = QuestHistory.query.filter_by(user_id=user_id, quest_id=quest_id).first()
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
                    progress_record = UserProgress.query.filter_by(user_id=user_id, quest_id=quest_id).first()
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
                
                db.session.commit()

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

    quest = db.session.get(Quest, quest_id)
    jp_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title)

    # Re-fetch full question objects for the template
    question_ids = [r['question_id'] for r in last_result['results']]
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    question_map = {q.id: q for q in questions}

    # Add the full question object back into the results
    for res in last_result['results']:
        q = question_map.get(res['question_id'])
        if q:
            question_view_model = {
                'id': q.id,
                'type': q.type,
                'text': q.text,
                'explanation': q.explanation
            }
            if q.type == 'svg_interactive':
                question_view_model['svg_content'] = q.choices
            # Convert newlines in explanation to <br> tags for HTML rendering
            if q.explanation:
                question_view_model['explanation'] = q.explanation.replace('\n', '<br>')

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
    return render_template('quest.html', quests=Quest)

# メダル表示用ルート
@app.route('/medals')
@login_required
def medals():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Aggregate attempts by title and level
    medal_data = db.session.query(
        Quest.title,
        Quest.level,
        func.sum(QuestHistory.attempts).label('total_attempts')
    ).join(
        Quest, Quest.id == QuestHistory.quest_id
    ).filter(
        QuestHistory.user_id == user_id
    ).group_by(
        Quest.title, Quest.level
    ).order_by(
        Quest.title, Quest.level
    ).all()

    # Apply Japanese mapping to titles
    processed_medal_data = []
    for title, level, total_attempts in medal_data:
        jp_title = SUBJECT_KEY_TO_JP.get(title, title)
        processed_medal_data.append((jp_title, level, total_attempts))

    return render_template("medals.html", medal_data=processed_medal_data)

# 進捗表示用ルート
@app.route('/progress')
@login_required
def progress():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # 1. Existing query for the summary table (preserved)
    cleared_counts = db.session.query(
        Quest.title,
        Quest.level,
        db.func.count(Quest.id)
    ).join(
        UserProgress, Quest.id == UserProgress.quest_id
    ).filter(
        UserProgress.user_id == user_id,
        UserProgress.status == 'cleared'
    ).group_by(
        Quest.title, Quest.level
    ).all()

    processed_cleared_data = []
    for title, level, count in cleared_counts:
        jp_title = SUBJECT_KEY_TO_JP.get(title, title)
        jp_level = SUBJECT_KEY_TO_JP.get(level, level)
        processed_cleared_data.append((jp_title, jp_level, count))

    # 2. New query for 4-week chart data
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
    weekly_data = db.session.query(
        func.strftime('%Y-%W', QuestAttemptLog.attempted_at).label('week'),
        func.sum(case((QuestAttemptLog.correct_answers == QuestAttemptLog.total_questions, 1), else_=0)).label('cleared_count'),
        func.count(QuestAttemptLog.id).label('attempt_count')
    ).filter(
        QuestAttemptLog.user_id == user_id,
        QuestAttemptLog.attempted_at >= four_weeks_ago
    ).group_by('week').order_by('week').all()

    weekly_chart_data = {
        'labels': [d.week for d in weekly_data],
        'cleared_count': [d.cleared_count for d in weekly_data],
        'attempt_count': [d.attempt_count for d in weekly_data]
    }

    # 3. New query for 3-month chart data
    three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)
    monthly_data = db.session.query(
        func.strftime('%Y-%m', QuestAttemptLog.attempted_at).label('month'),
        func.sum(case((QuestAttemptLog.correct_answers == QuestAttemptLog.total_questions, 1), else_=0)).label('cleared_count'),
        func.count(QuestAttemptLog.id).label('attempt_count')
    ).filter(
        QuestAttemptLog.user_id == user_id,
        QuestAttemptLog.attempted_at >= three_months_ago
    ).group_by('month').order_by('month').all()

    monthly_chart_data = {
        'labels': [d.month for d in monthly_data],
        'cleared_count': [d.cleared_count for d in monthly_data],
        'attempt_count': [d.attempt_count for d in monthly_data]
    }

    return render_template(
        "progress.html", 
        cleared=processed_cleared_data,
        weekly_chart_data=weekly_chart_data,
        monthly_chart_data=monthly_chart_data
    )

@app.route('/admin/students')
def manage_students():
    # ログインしているユーザーが管理者かチェック（適宜修正）
    if session.get('role') != 'admin' :
        return redirect(url_for('login'))

    users = User.query.filter_by(role='student').all()

    data = []

    for user in users:
        user_data = {
            'username': user.username,
            'nickname': user.nickname,  # ←これを必ず含めるように
            'progress': [],
            'medals': []
        }

        # 学習進捗状況の取得（UserProgressから）
        progress_query_result = db.session.query(
            Quest.title,
            Quest.level,
            db.func.count(Quest.id)
        ).join(UserProgress, Quest.id == UserProgress.quest_id) \
         .filter(UserProgress.user_id == user.id, UserProgress.status == 'cleared') \
         .group_by(Quest.title, Quest.level).all()

        # タイトルを日本語に変換
        processed_progress = []
        for p in progress_query_result:
            jp_title = SUBJECT_KEY_TO_JP.get(p[0], p[0])
            processed_progress.append({'title': jp_title, 'level': p[1], 'count': p[2]})
        user_data['progress'] = processed_progress

        # メダル取得状況の取得（挑戦回数の合計）
        medal_counts = db.session.query(
            QuestHistory.quest_id,
            QuestHistory.attempts
        ).filter_by(user_id=user.id).all()

        user_data['medals'] = [{'quest_id': m[0], 'count': m[1]} for m in medal_counts]

        data.append(user_data)

    return render_template('manage_students.html', students=data)

# クエストの一覧　追加・削除
@app.route('/manage_quests')
@login_required
def manage_quests():
    if not current_user.is_admin():
        return redirect(url_for(f"dashboard_{current_user.role}"))

    selected_title_jp = request.args.get('title', '')
    selected_level = request.args.get('level', '')

    # 全てのユニークなタイトルを取得
    all_titles_raw = db.session.query(Quest.title).distinct().all()
    jp_titles = sorted(list(set([SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in all_titles_raw])))

    # 全てのユニークなレベルを取得
    all_levels_raw = db.session.query(Quest.level).distinct().all()
    all_levels = sorted(list(set([l[0] for l in all_levels_raw])))

    quest_query = Quest.query
    if selected_title_jp:
        title_key = SUBJECT_JP_TO_KEY.get(selected_title_jp, selected_title_jp)
        quest_query = quest_query.filter_by(title=title_key)
    
    if selected_level:
        quest_query = quest_query.filter_by(level=selected_level)
    
    quests = quest_query.all()

    return render_template('list_quests.html', 
                           quests=quests, 
                           titles=jp_titles, 
                           selected_title=selected_title_jp,
                           levels=all_levels,
                           selected_level=selected_level)

#　クエストの編集・問題の追加
@app.route('/admin/quests/action', methods=['POST'])
@login_required
def handle_quest_action():
    action = request.form.get('action')
    quest_id = request.form.get('quest_id')
    title = request.form.get('title', '')
    level = request.form.get('level', '')

    if action == 'add':
        # Assuming 'add' goes to a new quest page that should also know how to get back
        return redirect(url_for('edit_quest', quest_id='new', title=title, level=level))
    
    # Actions that need a quest_id
    if not quest_id:
        flash("Questを選択してください", "warning")
        return redirect(url_for('manage_quests', title=title, level=level))

    if action == 'edit':
        return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))
    elif action == 'challenge':
        # Preserve title and level filters when challenging a quest from manage_quests
        return redirect(url_for('quest_run', quest_id=quest_id, title=title, level=level))
    elif action == 'delete':
        quest_id_to_delete = int(quest_id)
        quest = Quest.query.get(quest_id_to_delete)
        if quest:
            # Manually delete dependent records to prevent IntegrityError
            UserProgress.query.filter_by(quest_id=quest_id_to_delete).delete()
            QuestHistory.query.filter_by(quest_id=quest_id_to_delete).delete()
            Question.query.filter_by(quest_id=quest_id_to_delete).delete()

            db.session.delete(quest)
            db.session.commit()
            flash("削除しました", "success")
        return redirect(url_for('manage_quests', title=title, level=level))
    
    # Fallback just in case
    return redirect(url_for('manage_quests', title=title, level=level))

@app.route('/admin/quest/edit/<quest_id>', methods=['GET'])
@login_required
def edit_quest(quest_id):
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    if quest_id == 'new':
        quest = Quest(title=title, level=level, questname='') # Create a new quest object
    else:
        quest = Quest.query.get_or_404(int(quest_id))
    # Fetch all unique titles and levels for dropdowns
    all_titles_raw = db.session.query(Quest.title).distinct().all()
    all_titles_for_select = sorted([
        (SUBJECT_KEY_TO_JP.get(t[0], t[0]), t[0]) for t in all_titles_raw
    ], key=lambda x: x[0])

    all_levels = sorted(list(set([l[0] for l in db.session.query(Quest.level).distinct().all()])))

    quest_display_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title) if quest and quest.title else ''

    return render_template('edit_quest.html', quest=quest, quest_id=quest_id, 
                           title=title, level=level, 
                           all_titles=all_titles_for_select, # New: (JP_title, EN_key) tuples
                           all_levels=all_levels,
                           quest_display_title=quest_display_title)

# Quest情報の保存
@app.route('/admin/quest/save/<quest_id>', methods=['POST'])
def save_quest(quest_id):
    title = request.form.get('title')
    level = request.form.get('level')
    questname = request.form.get('questname')

    if quest_id == 'new':
        new_quest = Quest(title=title, level=level, questname=questname)
        db.session.add(new_quest)
        db.session.commit()
        flash("新しいクエストを保存しました", "success")
        # After saving, we redirect to the edit page of the *new* quest
        # We also pass the filters back so the "back" button works correctly
        return redirect(url_for('edit_quest', quest_id=new_quest.id, title=title, level=level))
    else:
        quest = Quest.query.get_or_404(int(quest_id))
        quest.title = title
        quest.level = level
        quest.questname = questname
        db.session.commit()
        flash("クエスト情報を保存しました", "success")
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
def delete_question(quest_id, question_id):
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    question = Question.query.get_or_404(question_id)
    db.session.delete(question)
    db.session.commit()
    flash("問題を削除しました", "success")
    return redirect(url_for('edit_quest', quest_id=quest_id, title=title, level=level))

# 新規Question作成画面
@app.route('/admin/question/add/<int:quest_id>')
def add_question(quest_id):
    quest = Quest.query.get_or_404(quest_id)
    title = request.args.get('title', '')
    level = request.args.get('level', '')
    return render_template('edit_question.html', question=None, quest=quest, quest_id=quest_id, title=title, level=level)

# 問題の編集画面
@app.route('/admin/question/edit/<int:quest_id>/<question_id>', methods=['GET'])
def edit_question(quest_id, question_id):
    quest = Quest.query.get_or_404(quest_id)
    title = request.args.get('title', '')
    level = request.args.get('level', '')

    if question_id == 'new':
        return render_template('edit_question.html', quest_id=quest.id, question=None, title=title, level=level)
    else:
        question = Question.query.get_or_404(int(question_id))
        choices = None
        answers = None
        if question.type == 'choice' or question.type == 'multiple_choice':
            choices = json.loads(question.choices) if question.choices else None
        elif question.type == 'numeric':
            try:
                answers = json.loads(question.answer) if question.answer else []
            except json.JSONDecodeError:
                answers = [] # Invalid JSON in DB, treat as empty
        elif question.type == 'svg_interactive':
            try:
                answers = json.loads(question.answer) if question.answer else []
            except json.JSONDecodeError:
                answers = [] # Invalid JSON in DB, treat as empty

        if question.type == 'function_graph' and question.answer:
            # Escape backslashes for the JavaScript template literal in edit_question.html
            question.answer = question.answer.replace('\\', '\\\\')

        # question.answers にセット（テンプレートで読みやすくする）
        if answers is not None:
            question.answers = answers

        # Debug log for sort type answer
        if question.type == 'sort':
            app.logger.debug(f"Edit Question (sort): question.answer = '{question.answer}'")

        return render_template('edit_question.html', quest_id=quest.id, question=question, choices=choices, answers=answers, title=title, level=level)

# 問題の保存画面
@app.route('/admin/question/save/<int:quest_id>/<question_id>', methods=['POST'])
def save_question(quest_id, question_id):
    title = request.form.get('title', '')
    level = request.form.get('level', '')

    action = request.form.get('action')

    if action == 'save_question':
        q_type = request.form['type']
        text = request.form['text']
        if question_id == 'new':
            question = Question(quest_id=quest_id, type=q_type, text=text)
        else:
            question = Question.query.get_or_404(int(question_id))
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
            sub_ids = request.form.getlist('sub_id')
            sub_prompts = request.form.getlist('sub_prompt')
            sub_answers = request.form.getlist('sub_answer')

            sub_questions = []
            for i in range(len(sub_ids)):
                if sub_ids[i] and sub_prompts[i] and sub_answers[i]:
                    sub_questions.append({
                        'id': sub_ids[i],
                        'prompt': sub_prompts[i],
                        'answer': sub_answers[i]
                    })

            question.choices = svg_content
            question.answer = json.dumps(sub_questions)

        elif q_type == 'function_graph':
            question.choices = None
            # The client-side JS already formats this into a JSON string.
            json_string_from_client = request.form.get('answer_function_graph', '[]')
            # Validate that it's valid JSON before saving.
            try:
                json.loads(json_string_from_client)
                question.answer = json_string_from_client
            except json.JSONDecodeError:
                question.answer = '[]'
                flash('方程式グラフのデータ形式が無効だったため、保存されませんでした。', 'error')

        if question_id == 'new':
            db.session.add(question)
        
        db.session.commit()
        flash('問題を保存しました', 'success')

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
        sub_ids = request.form.getlist('sub_id')
        sub_prompts = request.form.getlist('sub_prompt')
        sub_answers = request.form.getlist('sub_answer')
        
        sub_questions = []
        for i in range(len(sub_ids)):
            # Ensure all fields for a sub-question are present before adding
            if sub_prompts[i]:
                sub_questions.append({
                    'id': sub_ids[i],
                    'prompt': sub_prompts[i],
                    'answer': sub_answers[i]
                })
        question_data['sub_questions'] = sub_questions
        # The 'answer' field for svg_interactive in the database is the sub_questions JSON
        question_data['answer'] = sub_questions

    elif q_type == 'function_graph':
        json_string = request.form.get('answer_function_graph', '[]')
        try:
            # The answer is a list of function definitions
            question_data['answer'] = json.loads(json_string)
        except json.JSONDecodeError:
            question_data['answer'] = []

    return render_template('question_preview.html', question=question_data)


# タイトル一覧表示（ステップ1）
@app.route('/select_title_admin')
@login_required
def select_title_admin():
    titles = db.session.query(Quest.title).distinct().all()
    jp_titles = [SUBJECT_KEY_TO_JP.get(t[0], t[0]) for t in titles]
    return render_template('select_title_admin.html', titles=jp_titles)

# レベル選択（ステップ2）
@app.route('/select_level_admin/<title>')
@login_required
def select_level_admin(title):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    levels = db.session.query(Quest.level).filter_by(title=title_key).distinct().all()
    return render_template('select_level_admin.html', title=title, levels=[l[0] for l in levels])

@app.route('/select_quest_admin/<title>/<level>')
@login_required
def select_quest_by_title_level_admin(title, level):
    title_key = SUBJECT_JP_TO_KEY.get(title, title)
    quests = Quest.query.filter_by(title=title_key, level=level).all()
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
    quest = db.session.get(Quest, quest_id)
    if not quest:
        return "指定されたクエストが存在しません", 404

    # すべての同タイトルの問題を取得（1問＝1レコード）
    quest = Quest.query.filter_by(id=quest_id).first()  # ✅ 1件のQuestオブジェクトになる
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
        if q.type == 'svg_interactive':
            questions.append({
                "type": q.type,
                "text": q.text,
                "svg_content": q.choices, # choicesにSVGコンテンツを格納
                "sub_questions": json.loads(q.answer) # answerにサブ問題を格納
            })
        else:
            questions.append({
                "type": q.type,  
                "text": q.text,
                "choices": choices,
                "answer": answer if q.type != "numeric" else None,
                "answers": answer if q.type == "numeric" else None
            })

    jp_title = SUBJECT_KEY_TO_JP.get(quest.title, quest.title)
    return render_template("group_learning.html", quest_id=quest_id, quest=quest, title=jp_title, level=quest.level, questions=questions)

@app.route("/parent/students")
@login_required
def parent_students():
    if not current_user.is_parent():
        return redirect(url_for("dashboard"))

    parent_id = current_user.id
    children = User.query.filter_by(parent_id=parent_id, role="student").all()

    student_data = []
    for child in children:
        histories = QuestHistory.query.filter_by(user_id=child.id).all()
        total_medals = sum(h.attempts for h in histories)
        student_data.append({
            "student": child,
            "histories": histories,
            "medal_count": total_medals
        })

    return render_template("parent_students.html", student_data=student_data)

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
