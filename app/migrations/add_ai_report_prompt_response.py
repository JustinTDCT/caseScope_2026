#!/usr/bin/env python3
"""
Migration: Add prompt_sent and raw_response fields to AIReport table
Version: 1.10.44
Date: 2025-11-04
"""

import sqlite3
import sys
import os

DATABASE_PATH = '/opt/casescope/data/casescope.db'

def run_migration():
    """Add prompt_sent and raw_response columns to ai_report table"""
    
    print("Starting migration: Add prompt_sent and raw_response to ai_report table")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(ai_report)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'prompt_sent' not in columns:
            print("  Adding prompt_sent column...")
            cursor.execute("""
                ALTER TABLE ai_report 
                ADD COLUMN prompt_sent TEXT
            """)
            print("  ✅ Added prompt_sent column")
        else:
            print("  ℹ️  prompt_sent column already exists")
        
        if 'raw_response' not in columns:
            print("  Adding raw_response column...")
            cursor.execute("""
                ALTER TABLE ai_report 
                ADD COLUMN raw_response TEXT
            """)
            print("  ✅ Added raw_response column")
        else:
            print("  ℹ️  raw_response column already exists")
        
        conn.commit()
        print("✅ Migration completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

