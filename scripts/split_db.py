import sqlite3
import os
import shutil

def split_db():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_dir = os.path.join(base_dir, 'instance')
    
    # Ensure instance directory exists
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)
        
    old_db_path = os.path.join(base_dir, 'instance', 'mquest.db')
    if not os.path.exists(old_db_path):
        # Check root if not in instance (old behavior)
        old_db_path = os.path.join(base_dir, 'mquest.db')
        if not os.path.exists(old_db_path):
            print(f"Error: Original database not found at {old_db_path}")
            return

    user_db_path = os.path.join(instance_dir, 'mquest_user.db')
    content_db_path = os.path.join(instance_dir, 'mquest_content.db')

    print(f"Migrating data from {old_db_path}...")

    # Backup original
    shutil.copy2(old_db_path, old_db_path + '.bak')
    print(f"Backup created: {old_db_path}.bak")

    # Connect to databases
    old_conn = sqlite3.connect(old_db_path)
    user_conn = sqlite3.connect(user_db_path)
    content_conn = sqlite3.connect(content_db_path)

    # Tables for each DB
    user_tables = ['users', 'quest_history', 'user_progress', 'quest_attempt_logs']
    content_tables = ['quests', 'questions']

    def copy_table(table_name, src_conn, dst_conn):
        print(f"  Copying table: {table_name}")
        cursor = src_conn.cursor()
        
        # Get schema
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        schema = cursor.fetchone()
        if not schema:
            print(f"    Warning: Table {table_name} not found in source.")
            return
            
        dst_conn.execute(schema[0])
        
        # Get data
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        if rows:
            placeholders = ', '.join(['?' for _ in range(len(rows[0]))])
            dst_conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
        
        dst_conn.commit()

    # Copy tables
    for table in user_tables:
        copy_table(table, old_conn, user_conn)
        
    for table in content_tables:
        copy_table(table, old_conn, content_conn)

    old_conn.close()
    user_conn.close()
    content_conn.close()

    print("\nMigration completed successfully!")
    print(f"New user database: {user_db_path}")
    print(f"New content database: {content_db_path}")
    print(f"Original database preserved at {old_db_path}")

if __name__ == '__main__':
    split_db()
