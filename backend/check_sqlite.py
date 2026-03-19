import sqlite3
import os

db_path = "x:\\Varahe Analtics\\Productivity-Tracker\\backend\\tracker.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        res = cur.execute("SELECT count(*) as count FROM editor_context").fetchone()
        print(f"SQLite editor_context count: {res['count']}")
        
        # Check browser_context too
        res_browser = cur.execute("SELECT count(*) as count FROM browser_context").fetchone()
        print(f"SQLite browser_context count: {res_browser['count']}")
        
        # Check last recorded time in SQLite
        res_time = cur.execute("SELECT MAX(captured_at) as last_time FROM browser_context").fetchone()
        print(f"SQLite browser_context last_time: {res_time['last_time']}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print(f"Database not found at {db_path}")
