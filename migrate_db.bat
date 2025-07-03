chcp 65001

REM DBファイルを削除
del .\instance\mquest.db
REM DBファイルを作成
python models.py
REM 初期データ登録
python create_users.py
python add_sample_quests.py
