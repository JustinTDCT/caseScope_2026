"""
caseScope v9.5.0 - Modular File Processing Functions

This module contains the 4 core processing functions that operate on individual files:
1. duplicate_check() - Check if file already exists (hash + filename)
2. index_file() - Convert EVTX→JSON, count events, index to OpenSearch
3. chainsaw_file() - Run SIGMA rules and flag violations
4. hunt_iocs() - Search for IOCs and flag matches

Each function is standalone and can be called individually or as part of a pipeline.

Architecture:
- Worker Stack (normal upload): duplicate_check → index_file → chainsaw_file → hunt_iocs
- Single File Reindex: Clear all → index_file → chainsaw_file → hunt_iocs
- Single File Rechainsaw: Clear SIGMA → chainsaw_file
- Single File Rehunt: Clear IOC → hunt_iocs
- Bulk Operations: Clear all (bulk) → run function on each file
"""

import os
import json
import subprocess
import tempfile
import hashlib
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCTION 1: DUPLICATE CHECK
# ============================================================================

def duplicate_check(db, CaseFile, SkippedFile, case_id: int, filename: str, 
                   file_path: str, upload_type: str = 'http', exclude_file_id: int = None) -> dict:
    """
    Check if file already exists in case (hash + filename match).
    
    Logic:
    - If hash + filename match → Skip (duplicate)
    - If hash matches but filename different → Proceed (different source system)
    - If hash doesn't match → Proceed (new file)
    - If file has 0 events → Log and skip
    
    Args:
        db: SQLAlchemy database session
        CaseFile: CaseFile model class
        SkippedFile: SkippedFile model class
        case_id: Case ID
        filename: Original filename (e.g., "DESKTOP-123_Security.evtx")
        file_path: Full path to file on disk
        upload_type: 'http' or 'local'
    
    Returns:
        dict: {
            'status': 'skip' | 'proceed',
            'reason': str (if skip),
            'file_hash': str,
            'file_size': int
        }
    """
    logger.info("="*80)
    logger.info("[DUPLICATE CHECK] Starting duplicate check")
    logger.info(f"[DUPLICATE CHECK] Case: {case_id}, File: {filename}")
    logger.info("="*80)
    
    # Calculate file hash and size
    file_size = os.path.getsize(file_path)
    
    # Check for 0-byte files
    if file_size == 0:
        logger.warning(f"[DUPLICATE CHECK] File is 0 bytes, skipping: {filename}")
        
        # Log to skipped_file table
        skipped = SkippedFile(
            case_id=case_id,
            filename=filename,
            file_size=0,
            file_hash=None,
            skip_reason='zero_bytes',
            skip_details='File is 0 bytes (corrupt or empty)',
            upload_type=upload_type
        )
        db.session.add(skipped)
        db.session.commit()
        
        return {
            'status': 'skip',
            'reason': 'zero_bytes',
            'file_hash': None,
            'file_size': 0
        }
    
    # Calculate SHA256 hash
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    file_hash = sha256_hash.hexdigest()
    
    logger.info(f"[DUPLICATE CHECK] File hash: {file_hash[:16]}...")
    logger.info(f"[DUPLICATE CHECK] File size: {file_size:,} bytes")
    
    # Check for existing file with same hash + filename
    query = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        original_filename=filename,
        file_hash=file_hash,
        is_deleted=False
    )
    
    # v9.5.4: Exclude the current file being processed (don't match against self!)
    if exclude_file_id:
        query = query.filter(CaseFile.id != exclude_file_id)
    
    existing = query.first()
    
    if existing:
        logger.warning(f"[DUPLICATE CHECK] Duplicate found: hash + filename match (file_id={existing.id})")
        
        # Log to skipped_file table
        skipped = SkippedFile(
            case_id=case_id,
            filename=filename,
            file_size=file_size,
            file_hash=file_hash,
            skip_reason='duplicate_hash',
            skip_details=f'Duplicate of file_id {existing.id}',
            upload_type=upload_type
        )
        db.session.add(skipped)
        db.session.commit()
        
        return {
            'status': 'skip',
            'reason': 'duplicate_hash',
            'file_hash': file_hash,
            'file_size': file_size
        }
    
    logger.info("[DUPLICATE CHECK] ✓ No duplicate found, proceeding")
    return {
        'status': 'proceed',
        'reason': None,
        'file_hash': file_hash,
        'file_size': file_size
    }


# ============================================================================
# FUNCTION 2: INDEX FILE
# ============================================================================

def index_file(db, opensearch_client, CaseFile, Case, case_id: int, filename: str,
              file_path: str, file_hash: str, file_size: int, uploader_id: int,
              upload_type: str = 'http', file_id: int = None, celery_task=None, 
              use_event_descriptions: bool = True) -> dict:
    """
    Convert EVTX→JSON, count events, index to OpenSearch, update/create DB record.
    
    Process:
    1. Run evtx_dump to convert EVTX to JSONL (or use existing NDJSON)
    2. Count actual events from JSONL
    3. Index events to OpenSearch (bulk operation)
    4. Update existing CaseFile record OR create new one if file_id not provided
    5. Update Case aggregates (total_files, total_events)
    
    Args:
        db: SQLAlchemy database session
        opensearch_client: OpenSearch client instance
        CaseFile: CaseFile model class
        Case: Case model class
        case_id: Case ID
        filename: Original filename
        file_path: Full path to file on disk
        file_hash: SHA256 hash
        file_size: File size in bytes
        uploader_id: User ID of uploader
        upload_type: 'http' or 'local'
        celery_task: Celery task instance for progress updates (optional)
    
    Returns:
        dict: {
            'status': 'success' | 'error',
            'message': str,
            'file_id': int,
            'event_count': int,
            'index_name': str
        }
    """
    from utils import make_index_name
    from tasks import commit_with_retry
    
    logger.info("="*80)
    logger.info("[INDEX FILE] Starting file indexing")
    logger.info(f"[INDEX FILE] File: {filename}")
    logger.info("="*80)
    
    # Determine file type
    filename_lower = filename.lower()
    is_evtx = filename_lower.endswith('.evtx')
    is_json = filename_lower.endswith(('.json', '.ndjson', '.jsonl'))
    
    # Detect file type
    if filename_lower.endswith('.evtx'):
        file_type = 'EVTX'
    elif filename_lower.endswith('.ndjson'):
        file_type = 'NDJSON'
    elif filename_lower.endswith('.json'):
        file_type = 'JSON'
    elif filename_lower.endswith('.jsonl'):
        file_type = 'NDJSON'
    elif filename_lower.endswith('.csv'):
        file_type = 'CSV'
    else:
        file_type = 'UNKNOWN'
    
    is_csv = filename_lower.endswith('.csv')
    
    if not (is_evtx or is_json or is_csv):
        logger.error(f"[INDEX FILE] Unsupported file type: {filename}")
        return {
            'status': 'error',
            'message': f'Unsupported file type: {filename}',
            'file_id': None,
            'event_count': 0,
            'index_name': None
        }
    
    # Calculate size in MB (rounded)
    size_mb = round(file_size / (1024 * 1024))
    
    # Generate index name and opensearch_key
    index_name = make_index_name(case_id, filename)
    # Strip all JSON-related extensions for opensearch_key
    clean_name = filename.replace('.evtx', '').replace('.ndjson', '').replace('.jsonl', '').replace('.json', '')
    opensearch_key = f"case{case_id}_{clean_name}"
    
    logger.info(f"[INDEX FILE] File type: {file_type}")
    logger.info(f"[INDEX FILE] Size: {size_mb} MB ({file_size:,} bytes)")
    logger.info(f"[INDEX FILE] Target index: {index_name}")
    logger.info(f"[INDEX FILE] OpenSearch key: {opensearch_key}")
    
    # Use existing CaseFile record or create new one
    if file_id:
        logger.info(f"[INDEX FILE] Using existing CaseFile record: file_id={file_id}")
        case_file = db.session.get(CaseFile, file_id)
        if not case_file:
            logger.error(f"[INDEX FILE] CaseFile {file_id} not found!")
            return {
                'status': 'error',
                'message': f'CaseFile {file_id} not found',
                'file_id': None,
                'event_count': 0,
                'index_name': None
            }
        # Update existing record
        case_file.file_size = file_size
        case_file.size_mb = size_mb
        case_file.file_hash = file_hash
        case_file.file_type = file_type
        case_file.indexing_status = 'Indexing'
        case_file.is_indexed = False
        case_file.opensearch_key = opensearch_key
        logger.info(f"[INDEX FILE] Updated existing CaseFile record: file_id={file_id}")
    else:
        # Create new CaseFile record (status: Indexing)
        case_file = CaseFile(
            case_id=case_id,
            original_filename=filename,
            filename=os.path.basename(file_path),
            file_path=file_path,
            file_size=file_size,
            size_mb=size_mb,
            file_hash=file_hash,
            file_type=file_type,
            uploaded_by=uploader_id,
            indexing_status='Indexing',
            is_indexed=False,
            upload_type=upload_type,
            opensearch_key=opensearch_key
        )
        db.session.add(case_file)
        file_id = case_file.id
        logger.info(f"[INDEX FILE] Created new CaseFile record: file_id={file_id}")
    
    commit_with_retry(db.session, logger_instance=logger)
    
    try:
        # STEP 1: Convert EVTX to JSONL (if needed) or prepare CSV
        if is_evtx:
            logger.info("[INDEX FILE] Converting EVTX to JSONL...")
            json_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl')
            json_path = json_file.name
            json_file.close()
            
            # Run evtx_dump
            cmd = ['/opt/casescope/bin/evtx_dump', '-o', 'jsonl', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"[INDEX FILE] evtx_dump failed: {result.stderr[:200]}")
                case_file.indexing_status = 'Failed'
                commit_with_retry(db.session, logger_instance=logger)
                return {
                    'status': 'error',
                    'message': f'evtx_dump failed: {result.stderr[:100]}',
                    'file_id': file_id,
                    'event_count': 0,
                    'index_name': index_name
                }
            
            # Write JSONL to file
            with open(json_path, 'w') as f:
                f.write(result.stdout)
            
            logger.info(f"[INDEX FILE] ✓ EVTX converted to JSONL: {json_path}")
        elif is_csv:
            # CSV files will be processed directly (no conversion needed)
            json_path = None
            logger.info(f"[INDEX FILE] CSV file detected, will process directly")
        else:
            # Use existing JSON/NDJSON/JSONL file
            json_path = file_path
            logger.info(f"[INDEX FILE] Using existing JSON file: {json_path}")
        
        # STEP 2: Count events and index to OpenSearch
        logger.info("[INDEX FILE] Indexing events to OpenSearch...")
        
        # Create index with proper settings if it doesn't exist
        try:
            if not opensearch_client.indices.exists(index=index_name):
                opensearch_client.indices.create(
                    index=index_name,
                    body={
                        "settings": {
                            "index": {
                                "max_result_window": 100000  # Allow deep pagination
                            }
                        }
                    }
                )
                logger.info(f"[INDEX FILE] Created index {index_name} with max_result_window=100000")
            else:
                logger.info(f"[INDEX FILE] Index {index_name} already exists")
        except Exception as e:
            logger.error(f"[INDEX FILE] Failed to create index {index_name}: {e}")
            # CRITICAL: Cannot continue without a valid index
            case_file.indexing_status = f'Failed: {str(e)[:100]}'
            commit_with_retry(db.session, logger_instance=logger)
            return {
                'status': 'error',
                'message': f'Index creation failed: {e}',
                'file_id': file_id,
                'event_count': 0,
                'index_name': None
            }
        
        from opensearchpy.helpers import bulk as opensearch_bulk
        
        event_count = 0  # Events parsed from file
        indexed_count = 0  # Events successfully indexed to OpenSearch
        bulk_data = []
        
        # Process CSV files
        if is_csv:
            logger.info("[INDEX FILE] Processing CSV file...")
            import csv
            
            with open(file_path, 'r', encoding='utf-8-sig') as csvfile:  # utf-8-sig handles BOM
                # Detect delimiter and read CSV
                try:
                    sample = csvfile.read(8192)
                    csvfile.seek(0)
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample)
                    reader = csv.DictReader(csvfile, dialect=dialect)
                except:
                    # Fallback to standard comma delimiter
                    csvfile.seek(0)
                    reader = csv.DictReader(csvfile)
                
                row_num = 0
                for row in reader:
                    row_num += 1
                    
                    if not row or not any(row.values()):
                        continue
                    
                    # Convert CSV row to event dictionary
                    event = dict(row)
                    
                    # Add metadata
                    event['opensearch_key'] = opensearch_key
                    event['source_file_type'] = 'CSV'
                    event['row_number'] = row_num
                    
                    # Normalize event fields for consistent search
                    from event_normalization import normalize_event
                    event = normalize_event(event)
                    
                    bulk_data.append({
                        '_index': index_name,
                        '_source': event
                    })
                    
                    event_count += 1
                    
                    # Bulk index every 1000 events
                    if len(bulk_data) >= 1000:
                        try:
                            success, errors = opensearch_bulk(opensearch_client, bulk_data, raise_on_error=False)
                            indexed_count += success
                            if errors:
                                logger.warning(f"[INDEX FILE] {len(errors)} events failed to index in batch")
                        except Exception as e:
                            logger.error(f"[INDEX FILE] Bulk index error: {e}")
                        bulk_data = []
                        
                        # Update progress
                        if celery_task:
                            celery_task.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': event_count,
                                    'total': event_count,
                                    'status': f'Indexing {event_count:,} CSV rows'
                                }
                            )
                        
                        logger.info(f"[INDEX FILE] Progress: {event_count:,} CSV rows indexed")
            
            logger.info(f"[INDEX FILE] ✓ CSV processing complete: {event_count:,} rows")
        
        # Process JSON/NDJSON/EVTX files
        elif json_path:
            with open(json_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    
                    try:
                        event = json.loads(line)
                        
                        # Add opensearch_key for linking DB ↔ OpenSearch
                        event['opensearch_key'] = opensearch_key
                        
                        # Add source file type for filtering
                        if is_evtx:
                            event['source_file_type'] = 'EVTX'
                        else:
                            # Detect EDR vs generic JSON
                            is_edr = (
                                ('@timestamp' in event and ('process' in event or 'host' in event or 'agent' in event)) or
                                ('event' in event and isinstance(event.get('event'), dict) and 
                                 ('kind' in event['event'] or 'category' in event['event'])) or
                                'ecs' in event
                            )
                            event['source_file_type'] = 'EDR' if is_edr else 'JSON'
                        
                        # Normalize event fields (timestamp, computer, event_id) for consistent search
                        from event_normalization import normalize_event
                        event = normalize_event(event)
                        
                        # Add event description if available (Phase 3: Integration)
                        if use_event_descriptions:
                            try:
                                event_id = None
                                event_source = 'Security'  # Default
                                
                                # Extract event ID from event structure (handle both System and Event.System)
                                system_data = None
                                if 'System' in event:
                                    system_data = event['System']
                                elif 'Event' in event and isinstance(event['Event'], dict) and 'System' in event['Event']:
                                    system_data = event['Event']['System']
                                
                                if system_data and 'EventID' in system_data:
                                    event_id_data = system_data['EventID']
                                    if isinstance(event_id_data, dict) and '#text' in event_id_data:
                                        event_id = int(event_id_data['#text'])
                                    elif isinstance(event_id_data, int):
                                        event_id = event_id_data
                                    elif isinstance(event_id_data, str):
                                        event_id = int(event_id_data)
                                
                                # Extract channel/source
                                if system_data and 'Channel' in system_data:
                                    event_source = system_data['Channel']
                                
                                # Lookup event description
                                if event_id:
                                    from models import EventDescription
                                    event_desc = db.session.query(EventDescription).filter_by(
                                        event_id=event_id,
                                        event_source=event_source
                                    ).first()
                                    
                                    if event_desc:
                                        event['event_title'] = event_desc.title
                                        event['event_description'] = event_desc.description
                                        event['event_category'] = event_desc.category
                                        logger.debug(f"[INDEX FILE] Added description for Event ID {event_id}: {event_desc.title}")
                            except Exception as e:
                                # Don't fail indexing if description lookup fails
                                logger.warning(f"[INDEX FILE] Could not add event description: {e}")
                        
                        bulk_data.append({
                            '_index': index_name,
                            '_source': event
                        })
                        
                        event_count += 1
                        
                        # Bulk index every 1000 events
                        if len(bulk_data) >= 1000:
                            try:
                                success, errors = opensearch_bulk(opensearch_client, bulk_data, raise_on_error=False)
                                indexed_count += success
                                if errors:
                                    logger.warning(f"[INDEX FILE] {len(errors)} events failed to index in batch")
                            except Exception as e:
                                logger.error(f"[INDEX FILE] Bulk index error: {e}")
                            bulk_data = []
                            
                            # Update progress
                            if celery_task:
                                celery_task.update_state(
                                    state='PROGRESS',
                                    meta={
                                        'current': event_count,
                                        'total': event_count,  # Unknown total at this point
                                        'status': f'Indexing {event_count:,} events'
                                    }
                                )
                            
                            logger.info(f"[INDEX FILE] Progress: {event_count:,} events indexed")
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"[INDEX FILE] Skipping invalid JSON line {line_num}: {e}")
                        continue
        
        # Index remaining events
        if bulk_data:
            try:
                success, errors = opensearch_bulk(opensearch_client, bulk_data, raise_on_error=False)
                indexed_count += success
                if errors:
                    logger.warning(f"[INDEX FILE] {len(errors)} events failed to index in final batch")
            except Exception as e:
                logger.error(f"[INDEX FILE] Final bulk index error: {e}")
        
        logger.info(f"[INDEX FILE] ✓ Parsed {event_count:,} events, successfully indexed {indexed_count:,} to {index_name}")
        
        # Verify indexing success
        if indexed_count == 0 and event_count > 0:
            logger.error(f"[INDEX FILE] CRITICAL: Parsed {event_count} events but indexed 0! Index may not exist or bulk indexing failed.")
            case_file.indexing_status = 'Failed: 0 events indexed'
            case_file.event_count = 0
            commit_with_retry(db.session, logger_instance=logger)
            return {
                'status': 'error',
                'message': f'Indexing failed: 0 of {event_count} events indexed',
                'file_id': file_id,
                'event_count': 0,
                'index_name': index_name
            }
        
        # Use indexed_count (actual) instead of event_count (parsed)
        event_count = indexed_count
        
        # Check for 0 events OR JSON files with 0-1 events (CyLR artifacts)
        should_hide = False
        hide_reason = None
        
        if event_count == 0:
            should_hide = True
            hide_reason = "0 events"
        elif event_count == 1 and file_type == 'JSON' and not is_evtx:
            # JSON files (not EVTX-converted) with 1 event are CyLR artifacts
            should_hide = True
            hide_reason = "CyLR artifact (1 event)"
        
        if should_hide:
            logger.warning(f"[INDEX FILE] File has {hide_reason}, marking as hidden")
            case_file.indexing_status = 'Completed'
            case_file.is_indexed = True
            case_file.event_count = event_count
            case_file.is_hidden = True  # Auto-hide non-event files
            commit_with_retry(db.session, logger_instance=logger)
            
            # Clean up temp JSONL
            if is_evtx and os.path.exists(json_path):
                os.remove(json_path)
            
            return {
                'status': 'success',
                'message': 'File indexed but has 0 events (auto-hidden)',
                'file_id': file_id,
                'event_count': 0,
                'index_name': index_name
            }
        
        # STEP 3: Update CaseFile record
        case_file.event_count = event_count
        case_file.is_indexed = True
        commit_with_retry(db.session, logger_instance=logger)
        
        # STEP 4: Update Case aggregates
        case = db.session.get(Case, case_id)
        if case:
            case.total_files = db.session.query(CaseFile).filter_by(
                case_id=case_id, is_deleted=False
            ).count()
            
            from sqlalchemy import func
            case.total_events = db.session.query(func.sum(CaseFile.event_count)).filter_by(
                case_id=case_id, is_deleted=False
            ).scalar() or 0
            
            commit_with_retry(db.session, logger_instance=logger)
            logger.info(f"[INDEX FILE] ✓ Updated case aggregates: {case.total_files} files, {case.total_events:,} events")
        
        # Clean up temp JSONL
        if is_evtx and os.path.exists(json_path):
            os.remove(json_path)
        
        logger.info("[INDEX FILE] ✓ File indexing completed successfully")
        return {
            'status': 'success',
            'message': 'File indexed successfully',
            'file_id': file_id,
            'event_count': event_count,
            'index_name': index_name
        }
    
    except Exception as e:
        logger.error(f"[INDEX FILE] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        case_file.indexing_status = 'Failed'
        commit_with_retry(db.session, logger_instance=logger)
        
        return {
            'status': 'error',
            'message': str(e),
            'file_id': file_id,
            'event_count': 0,
            'index_name': index_name
        }


# ============================================================================
# FUNCTION 3: CHAINSAW FILE
# ============================================================================

def chainsaw_file(db, opensearch_client, CaseFile, SigmaRule, SigmaViolation,
                 file_id: int, index_name: str, celery_task=None) -> dict:
    """
    Run SIGMA rules against file events using Chainsaw and flag violations.
    
    v9.5.0: This function wraps the existing process_sigma_rules() implementation
    from tasks.py, which uses Chainsaw CLI for SIGMA processing.
    
    Process:
    1. Check if file is EVTX (skip if not)
    2. Get enabled SIGMA rules
    3. Run Chainsaw CLI against EVTX file
    4. Parse detections and create SigmaViolation records
    5. Update OpenSearch events with has_sigma_violation flag
    6. Update CaseFile.violation_count
    7. Update Case.total_events_with_SIGMA_violations
    
    Args:
        db: SQLAlchemy database session
        opensearch_client: OpenSearch client instance
        CaseFile: CaseFile model class
        SigmaRule: SigmaRule model class
        SigmaViolation: SigmaViolation model class
        file_id: CaseFile ID
        index_name: OpenSearch index name
        celery_task: Celery task instance for progress updates (optional)
    
    Returns:
        dict: {
            'status': 'success' | 'error',
            'message': str,
            'violations': int
        }
    """
    logger.info("="*80)
    logger.info("[CHAINSAW FILE] Starting SIGMA processing")
    logger.info(f"[CHAINSAW FILE] file_id={file_id}, index={index_name}")
    logger.info("="*80)
    
    # Get file record
    case_file = db.session.get(CaseFile, file_id)
    if not case_file:
        logger.error(f"[CHAINSAW FILE] File {file_id} not found")
        return {'status': 'error', 'message': 'File not found', 'violations': 0}
    
    # Only process EVTX files
    if not case_file.original_filename.lower().endswith('.evtx'):
        logger.info("[CHAINSAW FILE] Skipping SIGMA (not an EVTX file)")
        case_file.violation_count = 0
        from tasks import commit_with_retry
        commit_with_retry(db.session, logger_instance=logger)
        return {'status': 'success', 'message': 'Skipped (not EVTX)', 'violations': 0}
    
    # Update status
    case_file.indexing_status = 'SIGMA Testing'
    from tasks import commit_with_retry
    commit_with_retry(db.session, logger_instance=logger)
    
    # Setup paths
    import os
    import subprocess
    import tempfile
    import shutil
    import csv
    from pathlib import Path
    
    # Use existing sigma rules repo
    sigma_dir = Path("/opt/casescope/sigma_rules_repo")
    sigma_rules = sigma_dir / "rules" / "windows"
    
    # lolrmm rules (clone to home dir if not exists)
    home_dir = Path.home()
    lolrmm_dir = home_dir / "lolrmm"
    lolrmm_sigma = lolrmm_dir / "detections" / "sigma"
    
    # Rules cache directory
    cache_dir = Path("/opt/casescope/staging/.rules-merged")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    mapping_file = "/opt/casescope/chainsaw/mappings/sigma-event-logs-all.yml"
    chainsaw_bin = "/opt/casescope/bin/chainsaw"
    
    # Validate mapping file
    if not os.path.exists(mapping_file):
        logger.error(f"[CHAINSAW FILE] Mapping file not found: {mapping_file}")
        return {'status': 'error', 'message': 'Chainsaw mapping file not found', 'violations': 0}
    
    try:
        # Update SigmaHQ rules (already present at /opt/casescope/sigma_rules_repo)
        logger.info("[CHAINSAW FILE] Using existing SigmaHQ rules...")
        if (sigma_dir / ".git").exists():
            logger.info("[CHAINSAW FILE] Updating SigmaHQ rules...")
            subprocess.run(["git", "-C", str(sigma_dir), "pull", "--quiet"], 
                         check=False, capture_output=True, timeout=60)
        
        # Clone/update lolrmm rules
        logger.info("[CHAINSAW FILE] Ensuring lolrmm rules are present...")
        if (lolrmm_dir / ".git").exists():
            logger.info("[CHAINSAW FILE] Updating lolrmm rules...")
            subprocess.run(["git", "-C", str(lolrmm_dir), "pull", "--quiet"],
                         check=False, capture_output=True, timeout=60)
        elif not lolrmm_dir.exists():
            logger.info("[CHAINSAW FILE] Cloning lolrmm rules...")
            subprocess.run(["git", "clone", "--quiet", "--depth", "1",
                          "https://github.com/magicsword-io/lolrmm.git", str(lolrmm_dir)],
                         check=True, capture_output=True, timeout=300)
        
        # Validate rule directories exist
        if not sigma_rules.exists():
            logger.error(f"[CHAINSAW FILE] SigmaHQ Windows rules not found at: {sigma_rules}")
            return {'status': 'error', 'message': 'SigmaHQ rules not found', 'violations': 0}
        
        # Build merged rules cache (with file-based lock for concurrent workers)
        import fcntl
        lock_file = Path("/tmp/casescope_rules_cache.lock")
        lock_fd = None
        
        try:
            # Check if cache is already ready
            sigma_cache = cache_dir / "sigma"
            cache_ready = (cache_dir.exists() and 
                          sigma_cache.exists() and 
                          any(sigma_cache.rglob('*.yml')))
            
            if not cache_ready:
                # Acquire exclusive lock to build cache
                lock_fd = open(lock_file, 'w')
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
                
                # Double-check after acquiring lock (another worker may have built it)
                cache_ready = (cache_dir.exists() and 
                              sigma_cache.exists() and 
                              any(sigma_cache.rglob('*.yml')))
                
                if not cache_ready:
                    logger.info("[CHAINSAW FILE] Building merged rules cache...")
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy SigmaHQ Windows rules
                    shutil.copytree(sigma_rules, sigma_cache)
                    logger.info(f"[CHAINSAW FILE] Copied SigmaHQ Windows rules to cache ({sigma_cache})")
                    
                    # Copy specialized rule sets (DFIR, Emerging Threats, Threat Hunting)
                    additional_rules = [
                        (sigma_dir / "rules-dfir", cache_dir / "dfir"),
                        (sigma_dir / "rules-emerging-threats", cache_dir / "emerging-threats"),
                        (sigma_dir / "rules-threat-hunting", cache_dir / "threat-hunting"),
                    ]
                    
                    for source, dest in additional_rules:
                        if source.exists():
                            try:
                                shutil.copytree(source, dest)
                                rule_count = sum(1 for _ in dest.rglob('*.yml'))
                                logger.info(f"[CHAINSAW FILE] Copied {source.name} ({rule_count} rules) to cache")
                            except Exception as e:
                                logger.warning(f"[CHAINSAW FILE] Could not copy {source.name}: {e}")
                    
                    # Copy lolrmm rules if available
                    if lolrmm_sigma.exists():
                        lolrmm_cache = cache_dir / "lolrmm"
                        shutil.copytree(lolrmm_sigma, lolrmm_cache)
                        logger.info(f"[CHAINSAW FILE] Copied lolrmm rules to cache ({lolrmm_cache})")
                else:
                    logger.info("[CHAINSAW FILE] Rules cache already ready (built by another worker)")
            else:
                logger.info("[CHAINSAW FILE] Using existing rules cache")
        finally:
            # Release lock
            if lock_fd:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
        
        # Get the EVTX file path
        evtx_path = case_file.file_path
        if not os.path.exists(evtx_path):
            logger.error(f"[CHAINSAW FILE] EVTX file not found: {evtx_path}")
            return {'status': 'error', 'message': 'EVTX file not found', 'violations': 0}
        
        # Create temp output directory for chainsaw results
        with tempfile.TemporaryDirectory(prefix="chainsaw_") as tmpdir:
            logger.info(f"[CHAINSAW FILE] Running Chainsaw against {case_file.original_filename}...")
            
            # Run chainsaw
            cmd = [
                chainsaw_bin, "hunt",
                "--sigma", str(cache_dir),
                "--mapping", mapping_file,
                "--output", tmpdir,
                "--csv",
                evtx_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.warning(f"[CHAINSAW FILE] Chainsaw exit code: {result.returncode}")
                logger.warning(f"[CHAINSAW FILE] stderr: {result.stderr[:500]}")
            
            # Parse CSV output and count violations
            violations_found = []
            csv_files = list(Path(tmpdir).glob("*.csv"))
            
            logger.info(f"[CHAINSAW FILE] Found {len(csv_files)} CSV output file(s)")
            
            # Get SigmaRule model
            from main import SigmaRule
            
            # Cache for rule lookups (rule_title -> rule_id)
            rule_cache = {}
            
            for csv_file in csv_files:
                try:
                    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Extract rule name and level
                            rule_title = row.get('name', row.get('rule', row.get('Rule', 'Unknown')))
                            rule_level = row.get('level', row.get('Level', 'medium'))
                            
                            # Get or create SigmaRule
                            if rule_title not in rule_cache:
                                sigma_rule = db.session.query(SigmaRule).filter_by(title=rule_title).first()
                                if not sigma_rule:
                                    # Create new rule entry
                                    sigma_rule = SigmaRule(
                                        title=rule_title,
                                        description=row.get('description', row.get('Description', ''))[:500] or 'Detected by Chainsaw',
                                        rule_yaml='# Auto-generated from Chainsaw detection',
                                        level=rule_level,
                                        tags='[]',
                                        is_enabled=True
                                    )
                                    db.session.add(sigma_rule)
                                    db.session.flush()  # Get the ID
                                rule_cache[rule_title] = sigma_rule.id
                            
                            # Build event data JSON
                            event_data = {
                                'timestamp': row.get('timestamp', row.get('Timestamp', '')),
                                'computer': row.get('computer', row.get('Computer', '')),
                                'description': row.get('description', row.get('Description', ''))
                            }
                            
                            # Create violation record
                            violation_data = {
                                'case_id': case_file.case_id,
                                'file_id': file_id,
                                'rule_id': rule_cache[rule_title],
                                'event_id': row.get('Event ID', row.get('EventID', row.get('event_id', ''))),
                                'event_data': str(event_data),  # Store as JSON string
                                'matched_fields': '{}',  # Placeholder
                                'severity': rule_level
                            }
                            violations_found.append(violation_data)
                except Exception as e:
                    logger.warning(f"[CHAINSAW FILE] Error parsing CSV {csv_file.name}: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
            
            # Store violations in database
            violation_count = len(violations_found)
            logger.info(f"[CHAINSAW FILE] Found {violation_count} SIGMA violations")
            
            if violation_count > 0:
                # Delete existing violations for this file
                db.session.query(SigmaViolation).filter_by(file_id=file_id).delete()
                
                # Insert new violations
                for v in violations_found:
                    violation = SigmaViolation(**v)
                    db.session.add(violation)
                
                logger.info(f"[CHAINSAW FILE] Stored {violation_count} violations in database")
            
            # Update file violation count
            case_file.violation_count = violation_count
            commit_with_retry(db.session, logger_instance=logger)
            
            # Update case aggregate
            from main import Case
            case = db.session.get(Case, case_file.case_id)
            if case:
                from sqlalchemy import func
                case.total_events_with_SIGMA_violations = db.session.query(
                    func.sum(CaseFile.violation_count)
                ).filter_by(case_id=case.id, is_deleted=False).scalar() or 0
                commit_with_retry(db.session, logger_instance=logger)
            
            logger.info(f"[CHAINSAW FILE] ✓ SIGMA processing complete: {violation_count} violations")
            return {
                'status': 'success',
                'message': f'Found {violation_count} violations',
                'violations': violation_count
            }
    
    except subprocess.TimeoutExpired:
        logger.error("[CHAINSAW FILE] Chainsaw timed out")
        return {'status': 'error', 'message': 'Chainsaw timeout', 'violations': 0}
    except Exception as e:
        logger.error(f"[CHAINSAW FILE] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'status': 'error', 'message': str(e), 'violations': 0}


# ============================================================================
# FUNCTION 4: HUNT IOCS
# ============================================================================

def hunt_iocs(db, opensearch_client, CaseFile, IOC, IOCMatch, file_id: int,
             index_name: str, celery_task=None) -> dict:
    """
    Search for IOCs in file events (grep-like search) and flag matches.
    
    Process:
    1. Get active IOCs for case
    2. For each IOC, search OpenSearch (simple_query_string, case-insensitive)
    3. Create IOCMatch records
    4. Update OpenSearch events with has_ioc flag
    5. Update CaseFile.ioc_event_count
    6. Update Case.total_events_with_IOCs
    
    Args:
        db: SQLAlchemy database session
        opensearch_client: OpenSearch client instance
        CaseFile: CaseFile model class
        IOC: IOC model class
        IOCMatch: IOCMatch model class
        file_id: CaseFile ID
        index_name: OpenSearch index name (single file, e.g., "case2_file123")
        celery_task: Celery task instance for progress updates (optional)
    
    Returns:
        dict: {
            'status': 'success' | 'error',
            'message': str,
            'matches': int
        }
    """
    logger.info("="*80)
    logger.info("[HUNT IOCS] Starting IOC hunting (PER-FILE)")
    logger.info(f"[HUNT IOCS] file_id={file_id}, index={index_name}")
    logger.info(f"[HUNT IOCS] This searches ONLY ONE file's index!")
    logger.info("="*80)
    
    # Get file record
    case_file = db.session.get(CaseFile, file_id)
    if not case_file:
        logger.error(f"[HUNT IOCS] File {file_id} not found")
        return {'status': 'error', 'message': 'File not found', 'matches': 0}
    
    # Update status
    case_file.indexing_status = 'IOC Hunting'
    from tasks import commit_with_retry
    commit_with_retry(db.session, logger_instance=logger)
    
    # v9.5.10: Check if index exists before hunting (0-event files have no index)
    try:
        if not opensearch_client.indices.exists(index=index_name):
            logger.warning(f"[HUNT IOCS] Index {index_name} does not exist (0-event file?), skipping IOC hunt")
            case_file.ioc_event_count = 0
            case_file.indexing_status = 'Completed'
            commit_with_retry(db.session, logger_instance=logger)
            return {'status': 'success', 'message': 'Index does not exist (0-event file)', 'matches': 0}
    except Exception as e:
        logger.error(f"[HUNT IOCS] Error checking index existence: {e}")
        # Continue anyway - might be a transient error
    
    try:
        # Get active IOCs for this case
        iocs = db.session.query(IOC).filter_by(
            case_id=case_file.case_id,
            is_active=True
        ).all()
        
        if not iocs:
            logger.warning("[HUNT IOCS] No active IOCs found")
            case_file.ioc_event_count = 0
            commit_with_retry(db.session, logger_instance=logger)
            return {'status': 'success', 'message': 'No active IOCs', 'matches': 0}
        
        logger.info(f"[HUNT IOCS] Found {len(iocs)} active IOCs to hunt")
        
        total_matches = 0
        
        # IOC Type to Field Mapping (for targeted searches)
        # IMPORTANT: Most IOC types should search ALL fields (like grep does)
        # Only use targeted field searches for very specific cases where performance matters
        # 
        # SearchEVTX.sh does: grep -i -F "keyword" file.jsonl
        # This finds the IOC ANYWHERE in the JSON, not just specific fields!
        # 
        # Example: username "craigw" can appear in:
        #   - Event.EventData.SubjectUserName
        #   - Event.EventData.TargetUserName  
        #   - Event.EventData.User
        #   - Many other nested locations
        #
        # DEFAULT: Search all fields ["*"] to match grep behavior
        ioc_field_map = {
            # All IOC types now search all fields by default (like grep)
            # This ensures we find IOCs regardless of their location in nested JSON
        }
        
        # Process each IOC
        for idx, ioc in enumerate(iocs, 1):
            logger.info(f"[HUNT IOCS] Processing IOC {idx}/{len(iocs)}: {ioc.ioc_type}={ioc.ioc_value}")
            
            # Determine search fields based on IOC type
            # DEFAULT: Always search all fields ["*"] to match grep behavior
            # This ensures IOCs are found regardless of their location in nested JSON
            search_fields = ioc_field_map.get(ioc.ioc_type, ["*"])
            logger.info(f"[HUNT IOCS] Search fields for {ioc.ioc_type}: {search_fields} (using wildcard search for all nested fields)")
            
            # GREP-LIKE SEARCH: Case-insensitive, targeted or all fields
            # Use query_string for wildcard searches (supports nested objects)
            # Use simple_query_string for targeted field searches (better performance)
            if search_fields == ["*"]:
                # Wildcard search - use query_string to search nested objects
                # IMPORTANT: Must escape special Lucene characters for query_string
                def escape_lucene_special_chars(text):
                    """Escape special characters for Lucene query_string syntax
                    
                    IMPORTANT: Do NOT escape spaces! Spaces are natural word delimiters in Lucene.
                    When you escape a space as '\ ', it looks for a literal backslash-space combo.
                    
                    Example:
                      - Input: "powershell.exe -noprofile" 
                      - With space escaping: "*powershell\.exe\ \-noprofile*" ❌ Won't match
                      - Without space escaping: "*powershell\.exe*-noprofile*" ✅ Will match
                    """
                    special_chars = ['\\', '+', '-', '=', '&', '|', '!', '(', ')', '{', '}', 
                                     '[', ']', '^', '"', '~', '?', ':', '/']
                    # REMOVED: ' ' (space) from special_chars list
                    escaped = text
                    for char in special_chars:
                        if char != '*':  # Don't escape our wildcard
                            escaped = escaped.replace(char, f'\\{char}')
                    return escaped
                
                escaped_value = escape_lucene_special_chars(ioc.ioc_value)
                query = {
                    "query": {
                        "query_string": {
                            "query": f"*{escaped_value}*",
                            "default_operator": "AND",
                            "analyze_wildcard": True,
                            "lenient": True
                        }
                    }
                }
                logger.info(f"[HUNT IOCS] Using query_string for wildcard search (nested objects, escaped)")
            else:
                # Targeted field search - use simple_query_string
                query = {
                    "query": {
                        "simple_query_string": {
                            "query": ioc.ioc_value,
                            "fields": search_fields,
                            "default_operator": "and",
                            "lenient": True,
                            "analyze_wildcard": False
                        }
                    }
                }
                logger.info(f"[HUNT IOCS] Using simple_query_string for targeted field search")
            
            try:
                # Use scroll API to get ALL results (not limited to 10,000)
                # Initial search with scroll context
                scroll_query = query.copy()
                scroll_query['size'] = 5000  # Batch size per scroll
                
                response = opensearch_client.search(
                    index=index_name, 
                    body=scroll_query,
                    scroll='5m'  # Keep scroll context alive for 5 minutes
                )
                
                scroll_id = response.get('_scroll_id')
                all_hits = response['hits']['hits']
                total_hits = response['hits']['total']['value']
                
                # Continue scrolling if there are more results
                while len(all_hits) < total_hits and scroll_id:
                    response = opensearch_client.scroll(
                        scroll_id=scroll_id,
                        scroll='5m'
                    )
                    scroll_id = response.get('_scroll_id')
                    batch_hits = response['hits']['hits']
                    if not batch_hits:
                        break
                    all_hits.extend(batch_hits)
                
                # Clear scroll context
                if scroll_id:
                    try:
                        opensearch_client.clear_scroll(scroll_id=scroll_id)
                    except:
                        pass
                
                if all_hits:
                    logger.info(f"[HUNT IOCS] Found {len(all_hits)} matches for IOC: {ioc.ioc_value} (total: {total_hits})")
                    
                    # Create IOCMatch records in batches
                    import json
                    batch_size = 1000
                    for i in range(0, len(all_hits), batch_size):
                        batch = all_hits[i:i+batch_size]
                        
                        for hit in batch:
                            event_id = hit['_id']
                            event_source = hit['_source']
                            
                            # Store full event data as JSON
                            event_data_json = json.dumps(event_source)
                            
                            ioc_match = IOCMatch(
                                ioc_id=ioc.id,
                                case_id=case_file.case_id,
                                file_id=file_id,
                                event_id=event_id,
                                index_name=index_name,
                                matched_field=f'auto_detected_{ioc.ioc_type}',
                                event_data=event_data_json
                            )
                            db.session.add(ioc_match)
                            total_matches += 1
                        
                        commit_with_retry(db.session, logger_instance=logger)
                        logger.info(f"[HUNT IOCS] Committed batch {i//batch_size + 1} ({len(batch)} matches)")
                    
                    # Update OpenSearch events with has_ioc flag in batches
                    from opensearchpy.helpers import bulk as opensearch_bulk
                    for i in range(0, len(all_hits), batch_size):
                        batch = all_hits[i:i+batch_size]
                        bulk_updates = []
                        for hit in batch:
                            bulk_updates.append({
                                '_op_type': 'update',
                                '_index': index_name,
                                '_id': hit['_id'],
                                'doc': {'has_ioc': True}
                            })
                        
                        if bulk_updates:
                            opensearch_bulk(opensearch_client, bulk_updates)
                            logger.info(f"[HUNT IOCS] Updated OpenSearch batch {i//batch_size + 1} ({len(bulk_updates)} events)")
            
            except Exception as e:
                logger.error(f"[HUNT IOCS] Error searching for IOC {ioc.ioc_value}: {e}")
                continue
            
            # Update progress
            if celery_task:
                celery_task.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(iocs),
                        'status': f'IOC {idx}/{len(iocs)}'
                    }
                )
        
        # Update file IOC count
        case_file.ioc_event_count = total_matches
        commit_with_retry(db.session, logger_instance=logger)
        
        # Update case aggregates
        from main import Case
        case = db.session.get(Case, case_file.case_id)
        if case:
            from sqlalchemy import func
            case.total_events_with_IOCs = db.session.query(
                func.sum(CaseFile.ioc_event_count)
            ).filter_by(case_id=case.id, is_deleted=False).scalar() or 0
            commit_with_retry(db.session, logger_instance=logger)
        
        logger.info(f"[HUNT IOCS] ✓ Found {total_matches} IOC matches")
        return {
            'status': 'success',
            'message': f'Found {total_matches} matches',
            'matches': total_matches
        }
    
    except Exception as e:
        logger.error(f"[HUNT IOCS] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'status': 'error', 'message': str(e), 'matches': 0}

