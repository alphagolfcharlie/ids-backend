import sqlite3 
DB_name = 'crossings.db'
def init_db():
    conn = sqlite3.connect(DB_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crossings (
            destination TEXT,
            bdry_fix TEXT,
            restriction TEXT,
            notes TEXT,
            artcc TEXT
        )
    ''')
    crossings = [("EWR", "SLT", "AOB FL330", "", "ZNY")]

    cursor.executemany('INSERT INTO crossings VALUES (?, ?, ?, ?, ?)',crossings)
    conn.commit()
    conn.close()
init_db()