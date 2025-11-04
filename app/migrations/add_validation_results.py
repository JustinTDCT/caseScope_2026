#!/usr/bin/env python3
"""
Migration: Add validation_results field to AIReport table
Version: 1.10.46
Date: 2025-11-04
"""

import sqlite3
import sys
import os

DATABASE_PATH = '/opt/casescope/data/casescope.db'

def run_migration():
    """Add validation_results column to ai_report table"""
    
    print("Starting migration: Add validation_results to ai_report table")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(ai_report)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'validation_results' not in columns:
            print("  Adding validation_results column...")
            cursor.execute("""
                ALTER TABLE ai_report 
                ADD COLUMN validation_results TEXT
            """)
            print("  ✅ Added validation_results column")
        else:
            print("  ℹ️  validation_results column already exists")
        
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

