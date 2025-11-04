#!/usr/bin/env python3
"""
Database migration: Add stage tracking and cancellation support to AI reports

New fields:
- celery_task_id: Store Celery task ID for cancellation
- current_stage: Track generation stages (Initializing, Collecting Data, etc.)

Run this script to add the new columns to existing databases.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, db
from sqlalchemy import text

def migrate():
    """Add new columns to ai_report table"""
    with app.app_context():
        try:
            # Check if columns exist
            with db.engine.connect() as conn:
                # Add celery_task_id column
                try:
                    conn.execute(text("""
                        ALTER TABLE ai_report 
                        ADD COLUMN celery_task_id VARCHAR(255)
                    """))
                    print("✅ Added celery_task_id column")
                except Exception as e:
                    if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                        print("ℹ️  celery_task_id column already exists")
                    else:
                        raise
                
                # Add current_stage column
                try:
                    conn.execute(text("""
                        ALTER TABLE ai_report 
                        ADD COLUMN current_stage VARCHAR(50)
                    """))
                    print("✅ Added current_stage column")
                except Exception as e:
                    if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower():
                        print("ℹ️  current_stage column already exists")
                    else:
                        raise
                
                # Add index on celery_task_id
                try:
                    conn.execute(text("""
                        CREATE INDEX ix_ai_report_celery_task_id 
                        ON ai_report(celery_task_id)
                    """))
                    print("✅ Created index on celery_task_id")
                except Exception as e:
                    if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                        print("ℹ️  Index on celery_task_id already exists")
                    else:
                        raise
                
                conn.commit()
            
            print("\n✅ Migration completed successfully!")
            print("\nNew features enabled:")
            print("  • Task cancellation (revokes Celery task)")
            print("  • Stage tracking (Initializing → Collecting Data → Analyzing Data → Generating Report → Finalizing)")
            print("  • Cancel button in progress modal")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

if __name__ == '__main__':
    print("🔄 Starting database migration...")
    print("Adding stage tracking and cancellation support to AI reports\n")
    success = migrate()
    sys.exit(0 if success else 1)

