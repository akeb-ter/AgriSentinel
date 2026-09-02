import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'agrisentinel.db')

def init_db():
    # Only initialize if it doesn't exist
    if os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create logs table
    cursor.execute("""
    CREATE TABLE logs (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        PEST TEXT NOT NULL,
        RESULT TEXT NOT NULL,
        DATE TEXT NOT NULL,
        TIME TEXT NOT NULL
    )
    """)

    # Create pest table
    cursor.execute("""
    CREATE TABLE pest (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        PEST TEXT NOT NULL,
        DESCRIPTION TEXT NOT NULL,
        SUGGESTED_ACTION TEXT NOT NULL,
        SIGNAL_RANGE TEXT NOT NULL,
        IMAGE TEXT NOT NULL
    )
    """)

    # Create users_tbl
    cursor.execute("""
    CREATE TABLE users_tbl (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        LASTNAME TEXT NOT NULL,
        FIRSTNAME TEXT NOT NULL,
        MIDDLENAME TEXT NOT NULL,
        USER_TYPE TEXT NOT NULL,
        AFFILIATION TEXT NOT NULL,
        ACCOUNT TEXT NOT NULL,
        PASSWORD TEXT NOT NULL
    )
    """)

    # Insert default data
    cursor.execute("""
    INSERT INTO logs (PEST, RESULT, DATE, TIME) VALUES
    ('cricket', 'Detected', '2026-09-01', '01:21:27')
    """)

    cursor.execute("""
    INSERT INTO pest (PEST, DESCRIPTION, SUGGESTED_ACTION, SIGNAL_RANGE, IMAGE) VALUES
    ('cricket', 'cricket', 'cricket', 'High', 'images/1788216603_6a96051b8c979.jfif')
    """)

    # Note: Using plain text password here as per the original MySQL dump ('123')
    # In a real system, you'd hash this. For simplicity in migrating, we'll keep it as '123'
    # and handle it in the authentication route.
    cursor.execute("""
    INSERT INTO users_tbl (LASTNAME, FIRSTNAME, MIDDLENAME, USER_TYPE, AFFILIATION, ACCOUNT, PASSWORD) VALUES
    ('Labadia', 'Vicente', 'Beri', 'Administrator', 'Tacurong National High School', 'vicente.labadia@deped.gov.ph', '123')
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def get_db_connection():
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

if __name__ == '__main__':
    init_db()

