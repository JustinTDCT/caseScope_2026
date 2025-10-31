#!/usr/bin/env python3
"""
caseScope File Recovery Script
Detects and fixes files stuck in limbo after Celery worker crashes

Run this after worker crashes or restarts to recover stuck files.

Usage:
    python3 recover_limbo_files.py [--dry-run] [--case-id CASE_ID]

Detects:
- Files in processing states without active Celery tasks
- Files marked "Completed" but missing OpenSearch indices
- Files with event_count > 0 but is_indexed=False

Actions:
- Resets stuck files to "Queued" for reprocessing
- Marks invalid files as "Failed" with reason
- Optionally validates ALL "Completed" files
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

# Add app directory to path
sys.path.insert(0, '/opt/casescope/app')

from main import app, db, opensearch_client
from models import CaseFile
from utils import make_index_name
from celery_app import celery_app


def check_celery_task_active(task_id):
    """Check if a Celery task is actually running"""
    if not task_id:
        return False
    
    try:
        # Check task status
        result = celery_app.AsyncResult(task_id)
        # Task is active if it's pending or running
        return result.state in ['PENDING', 'STARTED', 'RETRY']
    except Exception as e:
        print(f"    WARNING: Could not check task {task_id}: {e}")
        return False


def validate_index_exists(case_id, filename):
    """Check if OpenSearch index exists for a file"""
    try:
        index_name = make_index_name(case_id, filename)
        exists = opensearch_client.indices.exists(index=index_name)
        return exists, index_name
    except Exception as e:
        print(f"    WARNING: Could not check index for {filename}: {e}")
        return None, None


def recover_limbo_files(case_id=None, dry_run=False, validate_all=False):
    """
    Detect and recover files stuck in limbo
    
    Args:
        case_id: Only check specific case (None = all cases)
        dry_run: Show what would be done without making changes
        validate_all: Validate ALL completed files for missing indices
    """
    print("="*80)
    print("caseScope File Recovery Script")
    print("="*80)
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    with app.app_context():
        # STEP 1: Find files in processing states
        print("\n[STEP 1] Checking for files in processing states...")
        print("-" * 80)
        
        query = db.session.query(CaseFile).filter(
            CaseFile.is_deleted == False,
            CaseFile.indexing_status.in_(['Queued', 'Indexing', 'SIGMA Testing', 'IOC Hunting'])
        )
        
        if case_id:
            query = query.filter(CaseFile.case_id == case_id)
        
        processing_files = query.all()
        print(f"Found {len(processing_files)} file(s) in processing states")
        
        stuck_count = 0
        for f in processing_files:
            # Check if task is actually running
            task_active = check_celery_task_active(f.celery_task_id)
            
            if not task_active:
                print(f"\n❌ STUCK FILE: {f.original_filename}")
                print(f"    ID: {f.id}")
                print(f"    Status: {f.indexing_status}")
                print(f"    Task ID: {f.celery_task_id or '(none)'}")
                print(f"    Uploaded: {f.uploaded_at}")
                
                if not dry_run:
                    f.indexing_status = 'Queued'
                    f.celery_task_id = None
                    print(f"    ✓ Reset to 'Queued' for reprocessing")
                else:
                    print(f"    WOULD: Reset to 'Queued'")
                
                stuck_count += 1
        
        if stuck_count == 0:
            print("✅ No stuck files found in processing states")
        else:
            print(f"\n⚠️  Found {stuck_count} stuck file(s)")
        
        # STEP 2: Validate completed files for missing indices
        print("\n[STEP 2] Validating completed files...")
        print("-" * 80)
        
        query = db.session.query(CaseFile).filter(
            CaseFile.is_deleted == False,
            CaseFile.is_hidden == False,  # Skip hidden files (they have no index intentionally)
            CaseFile.indexing_status == 'Completed',
            CaseFile.event_count > 0
        )
        
        if case_id:
            query = query.filter(CaseFile.case_id == case_id)
        
        if not validate_all:
            # Only check files uploaded in last 7 days
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            query = query.filter(CaseFile.uploaded_at >= cutoff_date)
            print(f"Checking files uploaded in last 7 days...")
        else:
            print(f"Checking ALL completed files (this may take a while)...")
        
        completed_files = query.all()
        print(f"Found {len(completed_files)} completed file(s) to validate")
        
        missing_index_count = 0
        for f in completed_files:
            exists, index_name = validate_index_exists(f.case_id, f.original_filename)
            
            if exists is False:  # Index does NOT exist
                print(f"\n❌ MISSING INDEX: {f.original_filename}")
                print(f"    ID: {f.id}")
                print(f"    Event Count: {f.event_count:,}")
                print(f"    Index Name: {index_name}")
                print(f"    Uploaded: {f.uploaded_at}")
                
                if not dry_run:
                    # Reset file for reprocessing
                    f.indexing_status = 'Queued'
                    f.celery_task_id = None
                    f.event_count = 0
                    f.violation_count = 0
                    f.ioc_event_count = 0
                    f.is_indexed = False
                    f.opensearch_key = None
                    print(f"    ✓ Reset to 'Queued' for full reprocessing")
                else:
                    print(f"    WOULD: Reset to 'Queued' for full reprocessing")
                
                missing_index_count += 1
        
        if missing_index_count == 0:
            print("✅ All completed files have valid OpenSearch indices")
        else:
            print(f"\n⚠️  Found {missing_index_count} file(s) with missing indices")
        
        # STEP 3: Check for inconsistent states
        print("\n[STEP 3] Checking for inconsistent states...")
        print("-" * 80)
        
        query = db.session.query(CaseFile).filter(
            CaseFile.is_deleted == False,
            CaseFile.is_hidden == False,
            CaseFile.event_count > 0,
            CaseFile.is_indexed == False
        )
        
        if case_id:
            query = query.filter(CaseFile.case_id == case_id)
        
        inconsistent_files = query.all()
        print(f"Found {len(inconsistent_files)} file(s) with event_count > 0 but is_indexed=False")
        
        for f in inconsistent_files:
            print(f"\n⚠️  INCONSISTENT: {f.original_filename}")
            print(f"    ID: {f.id}")
            print(f"    Event Count: {f.event_count}")
            print(f"    is_indexed: {f.is_indexed}")
            print(f"    Status: {f.indexing_status}")
            
            # Check if index actually exists
            exists, index_name = validate_index_exists(f.case_id, f.original_filename)
            
            if exists:
                # Index exists, just fix the flag
                print(f"    Index EXISTS: {index_name}")
                if not dry_run:
                    f.is_indexed = True
                    if f.indexing_status != 'Completed':
                        f.indexing_status = 'Completed'
                    print(f"    ✓ Fixed is_indexed flag")
                else:
                    print(f"    WOULD: Fix is_indexed flag")
            else:
                # Index missing, requeue
                print(f"    Index MISSING: {index_name}")
                if not dry_run:
                    f.indexing_status = 'Queued'
                    f.celery_task_id = None
                    f.event_count = 0
                    f.is_indexed = False
                    f.opensearch_key = None
                    print(f"    ✓ Reset for reprocessing")
                else:
                    print(f"    WOULD: Reset for reprocessing")
        
        # Commit changes
        if not dry_run and (stuck_count + missing_index_count + len(inconsistent_files)) > 0:
            db.session.commit()
            print(f"\n✅ Changes committed to database")
        
        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Stuck files (no active task):     {stuck_count}")
        print(f"Missing indices (data corruption): {missing_index_count}")
        print(f"Inconsistent states:               {len(inconsistent_files)}")
        print(f"Total files requiring attention:   {stuck_count + missing_index_count + len(inconsistent_files)}")
        
        if dry_run:
            print(f"\n🔍 DRY RUN COMPLETE - Run without --dry-run to apply fixes")
        else:
            print(f"\n✅ RECOVERY COMPLETE")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recover files stuck in limbo')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--case-id', type=int, help='Only check specific case')
    parser.add_argument('--validate-all', action='store_true', help='Validate ALL completed files (not just last 7 days)')
    
    args = parser.parse_args()
    
    try:
        recover_limbo_files(
            case_id=args.case_id,
            dry_run=args.dry_run,
            validate_all=args.validate_all
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Recovery interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

