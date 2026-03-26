import json

file_path = 'scripts/quests.json'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    modified_count = 0

    for quest_id, quest_data in data.items():
        if "questions" in quest_data:
            for question in quest_data["questions"]:
                if "answer" in question and isinstance(question["answer"], str):
                    # Check if the answer string in Python starts and ends with a double quote
                    # This means the original JSON had something like "answer": "\"value\""
                    original_answer_str = question["answer"]
                    if original_answer_str.startswith('"') and original_answer_str.endswith('"'):
                        # And it's not just a single double quote string
                        if len(original_answer_str) > 2:
                            question["answer"] = original_answer_str[1:-1]
                            modified_count += 1

    if modified_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully removed outer quotes from {modified_count} 'answer' fields in {file_path}")
    else:
        print(f"No 'answer' fields required modification in {file_path}")

except FileNotFoundError:
    print(f"Error: {file_path} not found.")
except json.JSONDecodeError as e:
    print(f"Error decoding JSON from {file_path}: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
