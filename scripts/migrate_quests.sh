#!/bin/bash
# This script Update quests.

# Change directory to the script's location to ensure python scripts are found
cd "$(dirname "$0")"

echo "[1/1] Updating quests..."
python ./add_sample_quests.py

echo
echo "Quests migration complete."
