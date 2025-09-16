from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from models import QuestHistory, Quest, Question
import json
import logging

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
    print(quests)
    return render_template(
        'select_quest.html',
        title=title,
        level=level,
        quests=quests
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
        # q.choicesが文字列のJSONならパースする
        try:
            choices = json.loads(q.choices)
        except Exception:
            choices = q.choices  # パースできなければそのまま

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
                "svg_content": json.loads(q.choices), # choicesにSVGコンテンツを格納
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

    return render_template("quest_run.html", quest_id=quest_id, quest=quest, title=SUBJECT_KEY_TO_JP.get(quest.title, quest.title), level=quest.level, questions=questions)

# クエストの結果を処理するエンドポイント
@app.route('/quest/<int:quest_id>/result', methods=['POST'])
def quest_result(quest_id):
    quest = db.session.get(Quest, quest_id)
    if not quest:
        return "Quest not found", 404

    results = []

    for i, q in enumerate(quest.questions):  # Question オブジェクト
        question_type = q.type
        question_text = q.text
        correct = False
        user_answer = ''
        expected = ''

        if question_type == 'choice':
            choices = json.loads(q.choices)
            answer_index = int(q.answer)
            user_answer = request.form.get(f'q{i}', '').strip()
            correct = user_answer == str(answer_index)
            expected = choices[answer_index]

        elif question_type == 'sort':
            user_answer = request.form.get(f'q{i}', '').strip()
            try:
                correct_answer = json.loads(q.answer)
            except (json.JSONDecodeError, TypeError):
                correct_answer = q.answer
            
            if isinstance(correct_answer, str):
                correct_answer = correct_answer.strip()

            correct = str(correct_answer) == user_answer
            expected = correct_answer

        elif question_type == 'fill_in_the_blank_en':
            user_answer = request.form.get(f'q{i}', '').strip().lower()
            try:
                correct_answer = json.loads(q.answer)
            except (json.JSONDecodeError, TypeError):
                correct_answer = q.answer
            correct = user_answer == correct_answer.lower()
            expected = correct_answer

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
            user_answer = user_input  # 表示用

        else:
            user_answer = ''
            correct = False
            expected = '未対応の形式'

        results.append({
            'question': question_text,
            'user_answer': user_answer,
            'correct': correct,
            'type': question_type,
            'expected': expected
        })

    all_correct = all(r['correct'] for r in results)
    level = quest.level

    user_id = session.get('user_id')
    if user_id:
        # ▼▼▼【世界制覇機能：クリア状況をUserProgressに保存】▼▼▼
        if all_correct:
            existing_progress = UserProgress.query.filter_by(user_id=user_id, quest_id=quest_id).first()
            if not existing_progress:
                progress = UserProgress(
                    user_id=user_id,
                    quest_id=quest_id,
                    status='cleared',
                    conquered_at=datetime.now(timezone.utc)
                )
                db.session.add(progress)
        # ▲▲▲【ここまで】▲▲▲

        # 履歴登録（既に全問正解があるなら重複しない）
        existing = QuestHistory.query.filter_by(user_id=user_id, quest_id=quest_id, correct=True).first()

        if existing:
            # 更新処理（例：attemptsと正解状況を更新）
            existing.attempts += 1
            existing.correct = correct  # 新しい結果に応じて更新（必要であれば）
            existing.last_attempt = datetime.now(timezone.utc)
        else:
            # 新規追加
            history = QuestHistory(
                user_id=user_id,
                quest_id=quest_id,
                correct=correct,
                is_cleared=False,
                attempts=1,
                last_attempt=datetime.now(timezone.utc)
            )
            db.session.add(history)
        
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            print("保存エラー:", e)


    return render_template("quest_result.html",
                           quest_id=quest_id,
                           quest=quest,
                           results=results,
                           all_correct=all_correct,
                           level=quest.level)


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
    from models import QuestHistory, Quest

    # quest_idごとの挑戦回数をカウント
    medal_data = db.session.query(
        QuestHistory.quest_id,
        Quest.title,
        db.func.count(QuestHistory.id)
    ).join(Quest, Quest.id == QuestHistory.quest_id
    ).filter(QuestHistory.user_id == user_id
    ).group_by(QuestHistory.quest_id).all()

    # Apply Japanese mapping to titles
    processed_medal_data = []
    for quest_id, title, attempts in medal_data:
        jp_title = SUBJECT_KEY_TO_JP.get(title, title)
        processed_medal_data.append((quest_id, jp_title, attempts))

    return render_template("medals.html", attempts=processed_medal_data)

# 進捗表示用ルート
@app.route('/progress')
@login_required
def progress():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # 各タイトル・レベルの全問正解数（1つの quest_id を1回のみカウント）
    cleared = db.session.query(
        Quest.title,
        Quest.level,
        db.func.count(db.distinct(QuestHistory.quest_id))
    ).join(Quest, Quest.id == QuestHistory.quest_id
    ).filter(
        QuestHistory.user_id == user_id,
        QuestHistory.correct == True
    ).group_by(Quest.title, Quest.level).all()

    # Apply Japanese mapping to titles and levels
    processed_cleared_data = []
    for title, level, count in cleared:
        jp_title = SUBJECT_KEY_TO_JP.get(title, title)
        jp_level = SUBJECT_KEY_TO_JP.get(level, level) # Assuming level might also need translation
        processed_cleared_data.append((jp_title, jp_level, count))

    return render_template("progress.html", cleared=processed_cleared_data)

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

        # 学習進捗状況の取得
        progress = db.session.query(
            Quest.title,
            Quest.level,
            db.func.count(QuestHistory.id)
        ).join(QuestHistory, Quest.id == QuestHistory.quest_id) \
         .filter(QuestHistory.user_id == user.id, QuestHistory.correct == True) \
         .group_by(Quest.title, Quest.level).all()

        user_data['progress'] = [{'title': p[0], 'level': p[1], 'count': p[2]} for p in progress]

        # メダル取得状況の取得（挑戦回数の合計）
        medal_counts = db.session.query(
            QuestHistory.quest_id,
            db.func.count(QuestHistory.id)
        ).filter_by(user_id=user.id) \
         .group_by(QuestHistory.quest_id).all() 

        user_data['medals'] = [{'quest_id': m[0], 'count': m[1]} for m in medal_counts]

        data.append(user_data)

    return render_template('manage_students.html', students=data)

# クエストの一覧　追加・削除
@app.route('/manage_quests')
@login_required
def manage_quests():
    if not current_user.is_admin():
        return redirect(url_for('dashboard'))

    quests = Quest.query.all()
    return render_template('list_quests.html', quests=quests)

#　クエストの編集・問題の追加
@app.route('/admin/quests/action', methods=['POST'])
@login_required
def handle_quest_action():
    action = request.form.get('action')
    quest_id = request.form.get('quest_id')

    if action == 'add':
        return redirect(url_for('edit_quest'))
    elif action == 'edit':
        if not quest_id:
            flash("Questを選択してください", "warning")
            return redirect(url_for('list_quests'))
        return redirect(url_for('edit_quest', quest_id=quest_id))
    elif action == 'delete':
        if not quest_id:
            flash("Questを選択してください", "warning")
            return redirect(url_for('list_quests'))
        quest = Quest.query.get(int(quest_id))
        if quest:
            db.session.delete(quest)
            db.session.commit()
            flash("削除しました", "success")
        return redirect(url_for('list_quests'))

@app.route('/admin/quest/edit/<int:quest_id>', methods=['GET'])
@login_required
def edit_quest(quest_id):
    quest = Quest.query.get_or_404(quest_id)
    return render_template('edit_quest.html', quest=quest,  quest_id=quest_id)

# Quest情報の保存
@app.route('/admin/quest/save/<int:quest_id>', methods=['POST'])
def save_quest(quest_id):
    quest = Quest.query.get_or_404(quest_id)
    quest.title = request.form.get('title')
    quest.level = request.form.get('level')
    db.session.commit()
    flash("クエスト情報を保存しました", "success")
    return redirect(url_for('edit_quest', quest_id=quest_id))

@app.route('/admin/question/edit/<int:quest_id>', methods=['POST'])
@login_required
def edit_question_action(quest_id):
    question_id = request.form.get('question_id')
    if question_id:
        return redirect(url_for('edit_question', quest_id=quest_id, question_id=question_id))
    flash("編集する問題を選択してください", "warning")
    return redirect(url_for('edit_quest', quest_id=quest_id))

@app.route('/admin/question/delete/<int:quest_id>', methods=['POST'])
@login_required
def delete_question_action(quest_id):
    question_id = request.form.get('question_id')
    if question_id:
        return redirect(url_for('delete_question', quest_id=quest_id, question_id=question_id))
    flash("削除する問題を選択してください", "warning")
    return redirect(url_for('edit_quest', quest_id=quest_id))

# Questionの削除
@app.route('/admin/question/delete/<int:question_id>', methods=['POST'])
def delete_question(quest_id, question_id):
    question = Question.query.get_or_404(question_id)
    quest_id = question.quest_id
    db.session.delete(question)
    db.session.commit()
    flash("問題を削除しました", "success")
    return redirect(url_for('edit_quest', quest_id=quest_id))

# 新規Question作成画面
@app.route('/admin/question/add/<int:quest_id>')
def add_question(quest_id):
    quest = Quest.query.get_or_404(quest_id)
    return render_template('edit_question.html', question=None, quest=quest)

# 問題の編集画面
@app.route('/admin/question/edit/<int:quest_id>/<question_id>', methods=['GET'])
def edit_question(quest_id, question_id):
    quest = Quest.query.get_or_404(quest_id)
    if question_id == 'new':
        return render_template('edit_question.html', quest_id=quest.id, question=None)
    else:
        question = Question.query.get_or_404(int(question_id))
        choices = json.loads(question.choices) if question.choices else None
        answers = json.loads(question.answer) if question.type == 'numeric' else None

        # question.answers にセット（テンプレートで読みやすくする）
        if answers is not None:
            question.answers = answers  # ✅ ここで直接属性にセット

        return render_template('edit_question.html', quest_id=quest.id, question=question, choices=choices, answers=answers)

# 問題の保存画面
@app.route('/admin/question/save/<int:quest_id>/<question_id>', methods=['POST'])
def save_question(quest_id, question_id):

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

        if q_type == 'choice':
            choices = [request.form.get(f'choice{i}', '') for i in range(4)]
            answer = int(request.form['answer'])
            question.choices = json.dumps(choices)
            question.answer = json.dumps(answer)

        elif q_type == 'sort':
            question.choices = None
            question.answer = request.form['answer_sort']

        elif q_type == 'numeric':
            answers = []
            for i in range(4):
                label = request.form.get(f'label{i}', '')
                value = request.form.get(f'num_answer{i}', '')
                if label and value:
                    answers.append({'label': label, 'answer': int(value)})
            question.choices = None
            question.answer = json.dumps(answers)

        db.session.add(question)
        db.session.commit()
        flash('問題を保存しました')

    return redirect(url_for('edit_quest', quest_id=quest_id))

# タイトル一覧表示（ステップ1）
@app.route('/select_title_admin')
@login_required
def select_title_admin():
    titles = db.session.query(Quest.title).distinct().all()
    return render_template('select_title_admin.html', titles=[t[0] for t in titles])

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
        # q.choicesが文字列のJSONならパースする
        try:
            choices = json.loads(q.choices)
        except Exception:
            choices = q.choices  # パースできなければそのまま

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
                "svg_content": json.loads(q.choices), # choicesにSVGコンテンツを格納
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

    return render_template("group_learning.html", quest_id=quest_id, quest=quest, title=quest.title, level=quest.level, questions=questions)

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
