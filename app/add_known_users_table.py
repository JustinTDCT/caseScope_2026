#!/usr/bin/env python3
"""
Database Migration: Add known_user table
Creates the KnownUser model table for tracking legitimate users in the environment
"""

import sys
sys.path.insert(0, '/opt/casescope/app')

from main import app, db
from models import KnownUser

def migrate():
    """Add known_user table"""
    with app.app_context():
        print("=" * 60)
        print("Database Migration: Add known_user table")
        print("=" * 60)
        print()
        
        # Check if table exists
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'known_user' in tables:
            print("✅ Table 'known_user' already exists")
            return
        
        try:
            # Create table
            print("Creating table 'known_user'...")
            KnownUser.__table__.create(db.engine)
            print("✅ Table 'known_user' created successfully")
            print()
            print("Table schema:")
            print("  - id (Integer, Primary Key)")
            print("  - username (String(255), Unique, Indexed)")
            print("  - user_type (String(20), Default: '-')")
            print("  - compromised (Boolean, Default: False)")
            print("  - added_method (String(20)) - 'manual' or 'csv'")
            print("  - added_by (Integer, Foreign Key to user.id)")
            print("  - created_at (DateTime)")
            print()
            print("=" * 60)
            print("Migration Complete!")
            print("=" * 60)
        
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise

if __name__ == '__main__':
    migrate()

