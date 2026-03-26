# diagnose_data.py
import json
import sqlite3
import os

def diagnose_answers(db_path='mquest.db'):
    """
    Reads and prints the 'answer' field for all questions of type 'function_graph'
    to diagnose their current format in the database.
    """
    if not os.path.exists(db_path):
        print(f"Database file not found at '{db_path}'. Trying 'instance/mquest.db'.")
        db_path = os.path.join('instance', 'mquest.db')
        if not os.path.exists(db_path):
             print(f"Database file not found at '{db_path}' either. Aborting.")
             return

    print(f"Diagnosing database: {db_path}")
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, answer FROM questions WHERE type = 'function_graph'")
        questions = cursor.fetchall()

        if not questions:
            print("\nNo questions with type 'function_graph' found in the database.")
            return

        print(f"\nFound {len(questions)} 'function_graph' question(s). Dumping their 'answer' fields:")
        print("-" * 40)

        for q_id, answer_str in questions:
            print(f"Question ID: {q_id}")
            print(f"  Raw Answer from DB: {answer_str}")
            try:
                # Try to parse it to see what it is
                parsed = json.loads(answer_str)
                print(f"  Successfully parsed as JSON. Type: {type(parsed)}")
                if isinstance(parsed, list):
                    print("  Format appears CORRECT (JSON list).")
                else:
                    print("  Format is UNEXPECTED (Valid JSON, but not a list).")
            except Exception as e:
                print(f"  Failed to parse as JSON. Error: {e}")
                print("  Format is INCORRECT (Not valid JSON).")
            print("-" * 40)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    diagnose_answers()
