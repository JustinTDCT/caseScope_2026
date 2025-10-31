#!/usr/bin/env python3
"""
Database Migration: Add created_by field to User table
Adds the created_by foreign key to track who created each user
"""

from main import app, db
from models import User
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("[MIGRATION] Adding created_by field to User table...")
        
        try:
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT COUNT(*) 
                FROM pragma_table_info('user') 
                WHERE name='created_by'
            """))
            count = result.scalar()
            
            if count > 0:
                print("✓ Column 'created_by' already exists. No migration needed.")
                return
            
            # Add created_by column
            db.session.execute(text("""
                ALTER TABLE user 
                ADD COLUMN created_by INTEGER 
                REFERENCES user(id)
            """))
            
            db.session.commit()
            print("✓ Successfully added 'created_by' column to User table")
            
            # Show current user count
            user_count = User.query.count()
            print(f"✓ Current user count: {user_count}")
            
        except Exception as e:
            db.session.rollback()
            print(f"✗ Migration failed: {e}")
            raise

if __name__ == '__main__':
    migrate()

