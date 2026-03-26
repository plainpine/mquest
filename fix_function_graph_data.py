# fix_function_graph_data.py
import json
import sqlite3
import os

def fix_function_graph_answers(db_path='mquest.db'):
    """
    Finds all questions of type 'function_graph' and ensures their
    'answer' field is in the correct JSON format.
    The expected format is a JSON array of objects, e.g., [{"fn": "y = 2x - 1"}].
    """
    if not os.path.exists(db_path):
        print(f"Database file not found at '{db_path}'. Please check the path.")
        # Fallback to instance folder path
        db_path = os.path.join('instance', 'mquest.db')
        if not os.path.exists(db_path):
             print(f"Database file not found at '{db_path}' either. Aborting.")
             return

    print(f"Processing database: {db_path}")
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Select all function_graph questions
        cursor.execute("SELECT id, answer FROM questions WHERE type = 'function_graph'")
        questions_to_fix = cursor.fetchall()

        if not questions_to_fix:
            print("No questions with type 'function_graph' found.")
            return

        updated_count = 0
        for q_id, answer_str in questions_to_fix:
            if not answer_str:
                continue

            # Check if the answer is already a valid JSON that is a list
            try:
                data = json.loads(answer_str)
                if isinstance(data, list):
                    # It's already in the correct format (or at least it's a list)
                    continue
            except (json.JSONDecodeError, TypeError):
                # This is the case we need to fix: the string is not valid JSON
                # or not a list.
                pass

            # If we're here, the answer_str is a plain string like "y = 2x - 1"
            print(f"Fixing question with ID: {q_id}. Old answer: '{answer_str}'")

            # Build the new JSON structure
            functions = []
            for line in answer_str.strip().split('\n'):
                line = line.strip()
                if line:
                    functions.append({"fn": line})
            
            new_answer_json = json.dumps(functions)

            # Update the database
            cursor.execute("UPDATE questions SET answer = ? WHERE id = ?", (new_answer_json, q_id))
            print(f"  -> New answer: '{new_answer_json}'")
            updated_count += 1

        if updated_count > 0:
            conn.commit()
            print(f"\nSuccessfully updated {updated_count} question(s).")
        else:
            print("\nNo questions needed fixing. All 'function_graph' answers are in the correct format.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    fix_function_graph_answers()
