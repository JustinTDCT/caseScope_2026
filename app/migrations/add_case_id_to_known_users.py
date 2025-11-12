"""
Migration: Add case_id to known_user table
Makes Known Users case-specific instead of global

Run with:
    python migrations/add_case_id_to_known_users.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, db
from models import KnownUser, Case

def migrate():
    """Add case_id column to known_user table"""
    with app.app_context():
        try:
            # Check if column already exists
            from sqlalchemy import inspect, text
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('known_user')]
            
            if 'case_id' in columns:
                print("✅ case_id column already exists in known_user table")
                return
            
            print("🔄 Adding case_id column to known_user table...")
            
            # Add case_id column (nullable first, we'll update it)
            db.session.execute(text("""
                ALTER TABLE known_user 
                ADD COLUMN case_id INTEGER REFERENCES "case"(id)
            """))
            
            # Get case 9 (or first case if case 9 doesn't exist)
            target_case = Case.query.get(9)
            if not target_case:
                print("⚠️  Case 9 not found. Looking for first case...")
                target_case = Case.query.first()
                if not target_case:
                    print("⚠️  No cases found. Creating default case...")
                    from datetime import datetime
                    target_case = Case(
                        name="Default Case",
                        description="Default case for migrated known users",
                        created_by=1  # Assuming admin user ID is 1
                    )
                    db.session.add(target_case)
                    db.session.flush()
            
            # Update all existing known users to belong to case 9 (or the found case)
            print(f"🔄 Assigning all existing known users to case {target_case.id} ({target_case.name})...")
            db.session.execute(text("""
                UPDATE known_user 
                SET case_id = :case_id 
                WHERE case_id IS NULL
            """), {'case_id': target_case.id})
            
            # Make case_id NOT NULL
            print("🔄 Making case_id NOT NULL...")
            db.session.execute(text("""
                ALTER TABLE known_user 
                ALTER COLUMN case_id SET NOT NULL
            """))
            
            # Drop old unique constraint on username (if exists)
            print("🔄 Dropping old unique constraint on username...")
            try:
                db.session.execute(text("""
                    ALTER TABLE known_user 
                    DROP CONSTRAINT IF EXISTS known_user_username_key
                """))
            except Exception as e:
                print(f"   Note: {e}")
            
            # Add new unique constraint on (case_id, username)
            print("🔄 Adding unique constraint on (case_id, username)...")
            db.session.execute(text("""
                ALTER TABLE known_user 
                ADD CONSTRAINT uq_known_user_case_username 
                UNIQUE (case_id, username)
            """))
            
            # Create index on case_id if it doesn't exist
            print("🔄 Creating index on case_id...")
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_known_user_case_id 
                ON known_user (case_id)
            """))
            
            db.session.commit()
            
            # Verify
            count = KnownUser.query.count()
            print(f"✅ Migration complete! {count} known users migrated to case {target_case.id}")
            print(f"   All existing users assigned to: {target_case.name} (ID: {target_case.id})")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    migrate()

