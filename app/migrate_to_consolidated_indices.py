#!/usr/bin/env python3
"""
Index Consolidation Migration Script
Version: 1.13.1

Migrates from per-file indices to per-case indices:
- OLD: case_{id}_{filename} (10,458 indices = 10,458 shards)
- NEW: case_{id} (7 indices = 7 shards)

Process:
1. For each case, create new consolidated index (case_{id})
2. Query all old indices for that case (case_{id}_*)
3. Copy events to new index with added source_file and file_id fields
4. Delete old indices after successful migration
5. Update DB records

Run with: sudo -u casescope /opt/casescope/venv/bin/python3 migrate_to_consolidated_indices.py
"""

import sys
import os
from datetime import datetime

# Add app directory to path
sys.path.insert(0, '/opt/casescope/app')

from main import app, db, opensearch_client
from models import Case, CaseFile
from opensearchpy.helpers import bulk as opensearch_bulk
from opensearchpy.helpers import scan as opensearch_scan


def migrate_case(case_id):
    """Migrate a single case from per-file indices to consolidated index"""
    
    with app.app_context():
        print(f"\n{'='*80}")
        print(f"Migrating Case {case_id}")
        print(f"{'='*80}")
        
        # Get case
        case = db.session.get(Case, case_id)
        if not case:
            print(f"❌ Case {case_id} not found")
            return False
        
        print(f"Case Name: {case.name}")
        
        # Get all files for this case
        files = CaseFile.query.filter_by(case_id=case_id, is_deleted=False, is_hidden=False).all()
        print(f"Files: {len(files)}")
        
        if not files:
            print(f"⚠️  No files to migrate")
            return True
        
        # New consolidated index name
        new_index = f"case_{case_id}"
        
        # Create new index if it doesn't exist
        try:
            if not opensearch_client.indices.exists(index=new_index):
                opensearch_client.indices.create(
                    index=new_index,
                    body={
                        "settings": {
                            "index": {
                                "max_result_window": 100000
                            }
                        }
                    }
                )
                print(f"✅ Created consolidated index: {new_index}")
            else:
                print(f"✅ Consolidated index exists: {new_index}")
        except Exception as e:
            print(f"❌ Failed to create index {new_index}: {e}")
            return False
        
        # Migrate each file
        total_events = 0
        total_migrated = 0
        old_indices_to_delete = []
        
        for idx, file in enumerate(files, 1):
            print(f"\n[{idx}/{len(files)}] {file.original_filename} (ID: {file.id})")
            
            # Old index name (per-file)
            from utils import sanitize_filename
            sanitized = sanitize_filename(file.original_filename)
            if '.' in sanitized:
                sanitized = sanitized.rsplit('.', 1)[0]
            old_index = f"case_{case_id}_{sanitized}"
            
            # Check if old index exists
            try:
                if not opensearch_client.indices.exists(index=old_index):
                    print(f"  ⚠️  Old index doesn't exist: {old_index} (skipping)")
                    continue
            except Exception as e:
                print(f"  ❌ Error checking index: {e}")
                continue
            
            # Get event count from old index
            try:
                old_count = opensearch_client.count(index=old_index)['count']
                print(f"  Events in old index: {old_count:,}")
                total_events += old_count
                
                if old_count == 0:
                    print(f"  ⚠️  Empty index, marking for deletion")
                    old_indices_to_delete.append(old_index)
                    continue
            except Exception as e:
                print(f"  ❌ Error counting events: {e}")
                continue
            
            # Copy events from old index to new index
            try:
                print(f"  Copying events...")
                
                # Use scroll API to get all events
                events_to_copy = []
                for event in opensearch_scan(
                    opensearch_client,
                    index=old_index,
                    query={"query": {"match_all": {}}},
                    scroll='5m',
                    size=1000
                ):
                    # Add source_file and file_id fields
                    source = event['_source']
                    source['source_file'] = file.original_filename
                    source['file_id'] = file.id
                    
                    # Prepare for bulk index
                    events_to_copy.append({
                        '_index': new_index,
                        '_id': event['_id'],  # Preserve document ID
                        '_source': source
                    })
                    
                    # Bulk index every 1000 events
                    if len(events_to_copy) >= 1000:
                        success, errors = opensearch_bulk(opensearch_client, events_to_copy, raise_on_error=False)
                        total_migrated += success
                        print(f"    Migrated {total_migrated:,} / {old_count:,} events...", end='\r')
                        events_to_copy = []
                
                # Index remaining events
                if events_to_copy:
                    success, errors = opensearch_bulk(opensearch_client, events_to_copy, raise_on_error=False)
                    total_migrated += success
                
                print(f"  ✅ Migrated {old_count:,} events to {new_index}")
                
                # Mark old index for deletion
                old_indices_to_delete.append(old_index)
                
            except Exception as e:
                print(f"  ❌ Error copying events: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Verify new index count
        try:
            new_count = opensearch_client.count(index=new_index)['count']
            print(f"\n{'='*80}")
            print(f"Migration Summary:")
            print(f"  Old indices total events: {total_events:,}")
            print(f"  New index events: {new_count:,}")
            print(f"  Match: {'✅ YES' if new_count == total_events else '❌ NO'}")
            
            if new_count != total_events:
                print(f"  ⚠️  Event count mismatch! Not deleting old indices.")
                return False
        except Exception as e:
            print(f"❌ Error verifying new index: {e}")
            return False
        
        # Delete old indices
        if old_indices_to_delete:
            print(f"\nDeleting {len(old_indices_to_delete)} old indices...")
            for old_index in old_indices_to_delete:
                try:
                    opensearch_client.indices.delete(index=old_index)
                    print(f"  ✅ Deleted {old_index}")
                except Exception as e:
                    print(f"  ❌ Failed to delete {old_index}: {e}")
        
        print(f"\n✅ Case {case_id} migration complete!")
        return True


def main():
    """Run migration for all cases"""
    
    print("="*80)
    print("INDEX CONSOLIDATION MIGRATION v1.13.1")
    print("="*80)
    print("OLD: case_{id}_{filename} (10K+ indices = 10K+ shards)")
    print("NEW: case_{id} (1 index per case = minimal shards)")
    print("="*80)
    
    with app.app_context():
        # Get all cases
        cases = Case.query.all()
        print(f"\nFound {len(cases)} cases to migrate")
        
        if not cases:
            print("No cases found!")
            return
        
        # Ask for confirmation
        response = input("\nContinue with migration? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled")
            return
        
        # Migrate each case
        success_count = 0
        failed_cases = []
        
        for case in cases:
            try:
                if migrate_case(case.id):
                    success_count += 1
                else:
                    failed_cases.append(case.id)
            except Exception as e:
                print(f"\n❌ Case {case.id} failed: {e}")
                import traceback
                traceback.print_exc()
                failed_cases.append(case.id)
        
        # Final summary
        print(f"\n{'='*80}")
        print("MIGRATION COMPLETE")
        print(f"{'='*80}")
        print(f"Success: {success_count}/{len(cases)} cases")
        
        if failed_cases:
            print(f"Failed: {failed_cases}")
        else:
            print("✅ All cases migrated successfully!")
        
        # Check final shard count
        try:
            stats = opensearch_client.cluster.stats()
            shard_count = stats['indices']['shards']['total']
            print(f"\nFinal shard count: {shard_count}")
        except:
            pass


if __name__ == '__main__':
    main()

