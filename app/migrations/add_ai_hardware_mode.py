#!/usr/bin/env python3
"""
Migration: Add AI Hardware Mode Setting
Date: 2025-11-05
Description: Adds 'ai_hardware_mode' setting to system_settings table with default 'cpu'
"""

import sys
sys.path.insert(0, '/opt/casescope/app')

from main import app, db
from models import SystemSettings

def migrate():
    """Add ai_hardware_mode setting"""
    with app.app_context():
        try:
            # Check if setting already exists
            existing = db.session.query(SystemSettings).filter_by(setting_key='ai_hardware_mode').first()
            
            if existing:
                print(f"✓ Setting 'ai_hardware_mode' already exists with value: {existing.setting_value}")
                return
            
            # Create new setting
            new_setting = SystemSettings(
                setting_key='ai_hardware_mode',
                setting_value='cpu',
                description='AI hardware mode: cpu or gpu (auto-optimizes settings for performance)'
            )
            
            db.session.add(new_setting)
            db.session.commit()
            
            print("✅ Migration successful!")
            print("   - Added 'ai_hardware_mode' setting with default value 'cpu'")
            print("   - This enables automatic optimization for CPU vs GPU hardware")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {e}")
            raise

if __name__ == '__main__':
    print("="*70)
    print("Migration: Add AI Hardware Mode Setting")
    print("="*70)
    migrate()
    print("="*70)

