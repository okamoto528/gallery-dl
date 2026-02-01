import sqlite3
import os
from datetime import datetime

DB_NAME = "organizer.db"

class DBManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Default to current directory or script directory
            self.db_path = DB_NAME
        else:
            self.db_path = db_path
        
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize the database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Galleries table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS galleries (
            id INTEGER PRIMARY KEY,
            title TEXT,
            original_filename TEXT,
            current_path TEXT,
            author TEXT,
            category TEXT,
            series TEXT,
            tags TEXT,
            language TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Author Settings table (for default category preference)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS author_settings (
            author_name TEXT PRIMARY KEY,
            default_category TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Author Aliases table (for name normalization)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS author_aliases (
            alias_name TEXT PRIMARY KEY,
            primary_author_name TEXT,
            FOREIGN KEY(primary_author_name) REFERENCES author_settings(author_name)
        )
        ''')

        # Categories table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY,
            display_order INTEGER DEFAULT 0
        )
        ''')
        
        # Migration: Check if display_order exists
        cursor.execute("PRAGMA table_info(categories)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'display_order' not in columns:
            cursor.execute("ALTER TABLE categories ADD COLUMN display_order INTEGER DEFAULT 0")
        
        # Seed default categories if empty
        cursor.execute("SELECT count(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            # name, display_order
            defaults = [
                ('Doujinshi', 10), 
                ('Manga', 20), 
                ('Game CG', 30), 
                ('Artist CG', 40), 
                ('Anime', 50), 
                ('Unknown', 999)
            ]
            cursor.executemany("INSERT INTO categories (name, display_order) VALUES (?, ?)", defaults)

        # Insert some initial data if needed, or just commit
        conn.commit()
        conn.close()

    # --- Gallery Operations ---

    def get_gallery_by_id(self, gallery_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM galleries WHERE id = ?", (gallery_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def upsert_gallery(self, data):
        """
        Insert or Update gallery metadata.
        data: dict containing keys matching table columns.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Prepare fields
        fields = ["id", "title", "original_filename", "current_path", "author", "category", "series", "tags", "language"]
        
        # Extract values, default to None
        values = [data.get(f) for f in fields]
        
        # Construct query
        placeholders = ", ".join(["?"] * len(fields))
        update_assignments = ", ".join([f"{f}=excluded.{f}" for f in fields])
        
        query = f'''
        INSERT INTO galleries ({", ".join(fields)}) VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {update_assignments}, imported_at=CURRENT_TIMESTAMP
        '''
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()

    # --- Author Settings Operations ---

    def get_author_category(self, author_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT default_category FROM author_settings WHERE author_name = ?", (author_name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def update_author_category(self, author_name, category):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO author_settings (author_name, default_category, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(author_name) DO UPDATE SET default_category=excluded.default_category, updated_at=CURRENT_TIMESTAMP
        ''', (author_name, category))
        conn.commit()
        conn.close()

    # --- Author Alias Operations ---

    def get_primary_author(self, author_name):
        """
        Returns the primary author name if an alias exists, otherwise returns the input name.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT primary_author_name FROM author_aliases WHERE alias_name = ?", (author_name,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        return author_name

    def add_alias(self, alias, primary):
        """Registers an alias."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO author_aliases (alias_name, primary_author_name)
        VALUES (?, ?)
        ''', (alias, primary))
        conn.commit()
        conn.close()

    # --- Category Operations ---

    def get_all_categories(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        # Order by display_order first, then name
        cursor.execute("SELECT name FROM categories ORDER BY display_order ASC, name ASC")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def add_category(self, name):
        if not name: return
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
