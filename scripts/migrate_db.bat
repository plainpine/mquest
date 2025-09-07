@echo off
REM This script rebuilds the entire database.

echo [1/3] Creating database schema...
python ./create_db.py

echo [2/3] Creating sample users...
python ./create_users.py

echo [3/3] Adding sample quests...
python ./add_sample_quests.py

echo.
echo Database migration complete.
