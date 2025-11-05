"""
Migration: Add ai_gpu_vram setting
Version: 1.10.72
Description: Adds GPU VRAM setting for model recommendations
"""
import sys
sys.path.insert(0, '/opt/casescope/app')

from main import app, db
from models import SystemSettings

def run_migration():
    """Add ai_gpu_vram setting"""
    with app.app_context():
        # Check if setting already exists
        existing = SystemSettings.query.filter_by(setting_key='ai_gpu_vram').first()
        
        if not existing:
            setting = SystemSettings(
                setting_key='ai_gpu_vram',
                setting_value='8',
                description='GPU VRAM in GB (for model recommendations)'
            )
            db.session.add(setting)
            db.session.commit()
            print("[Migration] ✓ Added ai_gpu_vram setting (default: 8GB)")
        else:
            print("[Migration] ✓ ai_gpu_vram setting already exists")
        
        return True

if __name__ == '__main__':
    try:
        success = run_migration()
        if success:
            print("[Migration] ✅ Migration completed successfully")
            sys.exit(0)
        else:
            print("[Migration] ❌ Migration failed")
            sys.exit(1)
    except Exception as e:
        print(f"[Migration] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

