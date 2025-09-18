#!/bin/bash
# This script rebuilds the entire database.

# Change directory to the script's location to ensure python scripts are found
cd "$(dirname "$0")"

echo "[1/3] Creating database schema..."
python ./create_db.py

echo "[2/3] Creating sample users..."
python ./create_users.py

echo "[3/3] Adding sample quests..."
python ./add_sample_quests.py

echo
echo "Database migration complete."
