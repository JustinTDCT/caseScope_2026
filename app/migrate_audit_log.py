#!/usr/bin/env python3
"""
Database Migration: Create audit_log table
Adds the audit trail table for tracking user actions
"""

from main import app, db
from models import AuditLog

def migrate():
    with app.app_context():
        print("[MIGRATION] Creating audit_log table...")
        
        try:
            # Create audit_log table
            db.create_all()
            
            # Verify table was created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'audit_log' in tables:
                print("✓ Successfully created audit_log table")
                
                # Show table structure
                columns = inspector.get_columns('audit_log')
                print(f"\n✓ Table structure ({len(columns)} columns):")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
            else:
                print("✗ audit_log table was not created")
                return False
            
            return True
            
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    migrate()

