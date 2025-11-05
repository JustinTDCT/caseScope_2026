#!/usr/bin/env python3
"""
Migration: Add Systems table for system identification and management
Version: 1.10.30
Date: 2025-11-05
"""

import sys
sys.path.insert(0, '/opt/casescope/app')

from main import app, db
from models import System

def run_migration():
    """Add systems table to database"""
    with app.app_context():
        print("[MIGRATION] Adding 'system' table...")
        
        try:
            # Create systems table
            db.create_all()
            print("✅ Systems table created successfully!")
            
            # Verify table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'system' in tables:
                print(f"✅ Verified: 'system' table exists")
                columns = [col['name'] for col in inspector.get_columns('system')]
                print(f"   Columns: {', '.join(columns)}")
            else:
                print("❌ ERROR: 'system' table not found after creation")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    print("="*60)
    print("MIGRATION: Add Systems Table")
    print("="*60)
    success = run_migration()
    sys.exit(0 if success else 1)

