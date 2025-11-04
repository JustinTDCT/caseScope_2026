#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Celery Tasks
Minimal task orchestrator - delegates to file_processing.py modular functions
"""

import os
import logging
from datetime import datetime

from celery_app import celery_app

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE HELPER
# ============================================================================

def commit_with_retry(session, max_retries=3, logger_instance=None):
    """Commit with retry logic for database locking"""
    import time
    for attempt in range(max_retries):
        try:
            session.commit()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                if logger_instance:
                    logger_instance.warning(f"DB commit failed (attempt {attempt+1}/{max_retries}), retrying...")
                time.sleep(0.5)
                session.rollback()
            else:
                if logger_instance:
                    logger_instance.error(f"DB commit failed after {max_retries} attempts")
                raise


# ============================================================================
# MAIN WORKER TASK - Orchestrates 4 modular functions
# ============================================================================

@celery_app.task(bind=True, name='tasks.process_file')
def process_file(self, file_id, operation='full'):
    """
    Process a file through the 4-step modular pipeline
    
    Steps:
    1. duplicate_check() - Skip if duplicate
    2. index_file() - EVTX→JSON→OpenSearch
    3. chainsaw_file() - SIGMA detection
    4. hunt_iocs() - IOC hunting
    
    Operations:
    - 'full': All 4 steps
    - 'reindex': Clear + re-index
    - 'chainsaw_only': SIGMA only
    - 'ioc_only': IOC only
    """
    from file_processing import duplicate_check, index_file, chainsaw_file, hunt_iocs
    from main import app, db
    from models import Case, CaseFile, SigmaRule, SigmaViolation, IOC, IOCMatch, SkippedFile
    from main import opensearch_client
    from utils import make_index_name
    
    logger.info(f"[TASK] Processing file_id={file_id}, operation={operation}")
    
    with app.app_context():
        try:
            # Get file record
            case_file = db.session.get(CaseFile, file_id)
            if not case_file:
                return {'status': 'error', 'message': 'File not found'}
            
            case = db.session.get(Case, case_file.case_id)
            if not case:
                return {'status': 'error', 'message': 'Case not found'}
            
            case_file.celery_task_id = self.request.id
            db.session.commit()
            
            index_name = make_index_name(case.id, case_file.original_filename)
            
            # FULL OPERATION
            if operation == 'full':
                # Step 1: Duplicate check
                dup_result = duplicate_check(
                    db=db,
                    CaseFile=CaseFile,
                    SkippedFile=SkippedFile,
                    case_id=case.id,
                    filename=case_file.original_filename,
                    file_path=case_file.file_path,
                    upload_type=case_file.upload_type or 'http',
                    exclude_file_id=file_id
                )
                
                if dup_result['status'] == 'skip':
                    case_file.indexing_status = 'Completed'
                    db.session.commit()
                    return {'status': 'success', 'message': 'Skipped (duplicate)'}
                
                # Step 2: Index file
                index_result = index_file(
                    db=db,
                    opensearch_client=opensearch_client,
                    CaseFile=CaseFile,
                    Case=Case,
                    case_id=case.id,
                    filename=case_file.original_filename,
                    file_path=case_file.file_path,
                    file_hash=dup_result['file_hash'],
                    file_size=dup_result['file_size'],
                    uploader_id=case_file.uploaded_by,
                    upload_type=case_file.upload_type,
                    file_id=file_id,  # Use existing CaseFile record
                    celery_task=self
                )
                
                if index_result['status'] == 'error':
                    case_file.indexing_status = 'Failed'
                    db.session.commit()
                    return index_result
                
                if index_result['event_count'] == 0:
                    # File already marked as hidden and indexed by file_processing.py
                    # No need to modify or commit again
                    return {'status': 'success', 'message': '0 events (hidden)'}
                
                # Step 3: SIGMA Testing (EVTX only)
                if case_file.original_filename.lower().endswith('.evtx'):
                    case_file.indexing_status = 'SIGMA Testing'
                    db.session.commit()
                    
                    chainsaw_result = chainsaw_file(
                        db=db,
                        opensearch_client=opensearch_client,
                        CaseFile=CaseFile,
                        SigmaRule=SigmaRule,
                        SigmaViolation=SigmaViolation,
                        file_id=file_id,
                        index_name=index_name,
                        celery_task=self
                    )
                else:
                    logger.info(f"[TASK] Skipping SIGMA (non-EVTX file): {case_file.original_filename}")
                    chainsaw_result = {'status': 'success', 'message': 'Skipped (non-EVTX)', 'violations': 0}
                
                # Step 4: IOC Hunting
                case_file.indexing_status = 'IOC Hunting'
                db.session.commit()
                
                ioc_result = hunt_iocs(
                    db=db,
                    opensearch_client=opensearch_client,
                    CaseFile=CaseFile,
                    IOC=IOC,
                    IOCMatch=IOCMatch,
                    file_id=file_id,
                    index_name=index_name,
                    celery_task=self
                )
                
                # CRITICAL: Validate index exists before marking "Completed"
                # Prevents data corruption if worker crashes during indexing
                if not case_file.is_hidden and case_file.event_count > 0:
                    try:
                        if not opensearch_client.indices.exists(index=index_name):
                            logger.error(f"[TASK] ❌ VALIDATION FAILED: Index {index_name} does not exist for file {file_id}")
                            logger.error(f"[TASK] ❌ File has event_count={case_file.event_count} but no index!")
                            logger.error(f"[TASK] ❌ Setting status to 'Failed' to prevent data corruption")
                            case_file.indexing_status = 'Failed: Index missing after processing'
                            case_file.celery_task_id = None
                            db.session.commit()
                            return {
                                'status': 'error',
                                'message': 'Index validation failed - index does not exist',
                                'file_id': file_id
                            }
                    except Exception as e:
                        logger.error(f"[TASK] ❌ Index validation error: {e}")
                        # Continue anyway - might be OpenSearch connectivity issue
                
                # Mark as completed
                case_file.indexing_status = 'Completed'
                case_file.celery_task_id = None
                db.session.commit()
                
                logger.info(f"[TASK] ✓ File {file_id} completed successfully (events={index_result['event_count']}, violations={chainsaw_result.get('violations', 0)}, ioc_matches={ioc_result.get('matches', 0)})")
                
                return {
                    'status': 'success',
                    'message': 'Processing completed',
                    'stats': {
                        'events': index_result['event_count'],
                        'violations': chainsaw_result.get('violations', 0),
                        'ioc_matches': ioc_result.get('matches', 0)
                    }
                }
            
            # CHAINSAW ONLY
            elif operation == 'chainsaw_only':
                from models import SigmaViolation
                db.session.query(SigmaViolation).filter_by(case_file_id=file_id).delete()
                db.session.commit()
                
                result = chainsaw_file(
                    db=db,
                    opensearch_client=opensearch_client,
                    CaseFile=CaseFile,
                    SigmaRule=SigmaRule,
                    SigmaViolation=SigmaViolation,
                    file_id=file_id,
                    index_name=index_name,
                    celery_task=self
                )
                
                case_file.indexing_status = 'Completed'
                db.session.commit()
                return result
            
            # IOC ONLY
            elif operation == 'ioc_only':
                from models import IOCMatch
                db.session.query(IOCMatch).filter(IOCMatch.index_name == index_name).delete()
                db.session.commit()
                
                result = hunt_iocs(
                    db=db,
                    opensearch_client=opensearch_client,
                    CaseFile=CaseFile,
                    IOC=IOC,
                    IOCMatch=IOCMatch,
                    file_id=file_id,
                    index_name=index_name,
                    celery_task=self
                )
                
                case_file.indexing_status = 'Completed'
                db.session.commit()
                return result
            
            else:
                return {'status': 'error', 'message': f'Unknown operation: {operation}'}
        
        except Exception as e:
            logger.error(f"[TASK] ❌ Processing failed for file_id={file_id}: {e}", exc_info=True)
            try:
                case_file = db.session.get(CaseFile, file_id)
                if case_file:
                    error_msg = str(e)[:150]  # Truncate long error messages
                    case_file.indexing_status = f'Failed: {error_msg}'
                    case_file.celery_task_id = None  # Clear task ID so file can be re-queued
                    db.session.commit()
                    logger.error(f"[TASK] ❌ File {file_id} marked as 'Failed' (can be re-queued)")
            except Exception as db_error:
                logger.error(f"[TASK] ❌ Could not update file status: {db_error}")
            return {'status': 'error', 'message': str(e), 'file_id': file_id}


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@celery_app.task(bind=True, name='tasks.bulk_reindex')
def bulk_reindex(self, case_id):
    """Re-index all files in a case (clears OpenSearch data and DB metadata first)"""
    from main import app, db, opensearch_client
    from bulk_operations import (
        get_case_files, clear_case_opensearch_indices, 
        clear_case_sigma_violations, clear_case_ioc_matches,
        clear_case_timeline_tags, reset_file_metadata, queue_file_processing
    )
    
    with app.app_context():
        # Get all files for case (exclude deleted and hidden files)
        # Hidden files = 0-event files or CyLR artifacts, no point re-indexing
        files = get_case_files(db, case_id, include_deleted=False, include_hidden=False)
        
        if not files:
            return {'status': 'success', 'message': 'No files to reindex', 'files_queued': 0}
        
        # Clear all OpenSearch indices for this case
        indices_deleted = clear_case_opensearch_indices(opensearch_client, case_id, files)
        
        # Clear all SIGMA violations, IOC matches, and timeline tags for this case
        sigma_deleted = clear_case_sigma_violations(db, case_id)
        ioc_deleted = clear_case_ioc_matches(db, case_id)
        tags_deleted = clear_case_timeline_tags(db, case_id)
        
        # Reset all file metadata (including opensearch_key)
        for f in files:
            reset_file_metadata(f, reset_opensearch_key=True)
        
        commit_with_retry(db.session, logger_instance=logger)
        logger.info(f"[BULK REINDEX] Reset metadata for {len(files)} files")
        
        # Queue full re-processing (index + SIGMA + IOC)
        queued = queue_file_processing(process_file, files, operation='full')
        
        return {
            'status': 'success',
            'files_queued': queued,
            'indices_deleted': indices_deleted,
            'sigma_cleared': sigma_deleted,
            'ioc_cleared': ioc_deleted,
            'timeline_tags_cleared': tags_deleted
        }


@celery_app.task(bind=True, name='tasks.bulk_rechainsaw')
def bulk_rechainsaw(self, case_id):
    """Re-run SIGMA on all files in a case (clears old violations first)"""
    from main import app, db
    from bulk_operations import (
        get_case_files, clear_case_sigma_violations, queue_file_processing
    )
    
    with app.app_context():
        # Clear all existing SIGMA violations for this case
        sigma_deleted = clear_case_sigma_violations(db, case_id)
        
        # Get indexed files only (exclude deleted and hidden files)
        files = get_case_files(db, case_id, include_deleted=False, include_hidden=False)
        files = [f for f in files if f.is_indexed]
        
        if not files:
            return {'status': 'success', 'message': 'No indexed files to process', 'files_queued': 0}
        
        # Reset violation_count and set status to Queued for all files
        for f in files:
            f.violation_count = 0
            f.indexing_status = 'Queued'
            f.celery_task_id = None
        
        commit_with_retry(db.session, logger_instance=logger)
        logger.info(f"[BULK RECHAINSAW] Reset violation_count and status to 'Queued' for {len(files)} files")
        
        # Queue re-chainsaw tasks
        queued = queue_file_processing(process_file, files, operation='chainsaw_only')
        
        return {'status': 'success', 'files_queued': queued, 'violations_cleared': sigma_deleted}


@celery_app.task(bind=True, name='tasks.bulk_rehunt')
def bulk_rehunt(self, case_id):
    """Re-hunt IOCs on all files in a case (clears old matches first)"""
    from main import app, db, opensearch_client
    from bulk_operations import (
        get_case_files, clear_case_ioc_matches, clear_case_ioc_flags_in_opensearch, queue_file_processing
    )
    
    with app.app_context():
        # IMPORTANT: Clear OpenSearch caches before bulk IOC hunting
        # This prevents circuit breaker errors due to high heap usage
        try:
            logger.info(f"[BULK REHUNT] Clearing OpenSearch caches before IOC hunt...")
            opensearch_client.indices.clear_cache(
                index='*',
                fielddata=True,
                query=True,
                request=True
            )
            logger.info(f"[BULK REHUNT] ✓ OpenSearch caches cleared successfully")
        except Exception as e:
            logger.warning(f"[BULK REHUNT] Failed to clear OpenSearch cache: {e}")
        
        # Get files first (needed for clearing OpenSearch flags)
        files = get_case_files(db, case_id, include_deleted=False, include_hidden=False)
        files = [f for f in files if f.is_indexed]
        
        if not files:
            return {'status': 'success', 'message': 'No indexed files to process', 'files_queued': 0}
        
        # Clear all existing IOC matches for this case (database)
        ioc_deleted = clear_case_ioc_matches(db, case_id)
        
        # CRITICAL: Clear has_ioc flags from OpenSearch indices
        # This ensures old IOC flags don't persist after re-hunt
        flags_cleared = clear_case_ioc_flags_in_opensearch(opensearch_client, case_id, files)
        
        # Reset ioc_event_count and set status to Queued for all files
        for f in files:
            f.ioc_event_count = 0
            f.indexing_status = 'Queued'
            f.celery_task_id = None
        
        commit_with_retry(db.session, logger_instance=logger)
        logger.info(f"[BULK REHUNT] Reset ioc_event_count and status to 'Queued' for {len(files)} files")
        
        # Queue re-hunt tasks
        queued = queue_file_processing(process_file, files, operation='ioc_only')
        
        return {'status': 'success', 'files_queued': queued, 'matches_cleared': ioc_deleted, 'flags_cleared': flags_cleared}


@celery_app.task(bind=True, name='tasks.single_file_rehunt')
def single_file_rehunt(self, file_id):
    """Re-hunt IOCs on a single file (clears old matches first)"""
    from main import app, db
    from models import CaseFile
    from bulk_operations import clear_file_ioc_matches, queue_file_processing
    
    with app.app_context():
        case_file = db.session.get(CaseFile, file_id)
        if not case_file:
            return {'status': 'error', 'message': 'File not found'}
        
        # Clear existing IOC matches for this file
        ioc_deleted = clear_file_ioc_matches(db, file_id)
        
        # Reset ioc_event_count and set status to Queued
        case_file.ioc_event_count = 0
        case_file.indexing_status = 'Queued'
        case_file.celery_task_id = None
        commit_with_retry(db.session, logger_instance=logger)
        
        # Queue re-hunt task
        queue_file_processing(process_file, [case_file], operation='ioc_only')
        
        return {'status': 'success', 'file_id': file_id, 'matches_cleared': ioc_deleted}


# ============================================================================
# BULK IMPORT TASK - Process files from local directory
# ============================================================================

@celery_app.task(bind=True, name='tasks.bulk_import_directory')
def bulk_import_directory(self, case_id):
    """
    Process all files from bulk import directory
    
    Reuses upload_pipeline functions for consistency:
    - Scans /opt/casescope/bulk_import/ directory
    - Stages files (with ZIP extraction)
    - Builds file queue (deduplication)
    - Queues for processing
    
    Args:
        case_id: Target case ID
        
    Returns:
        Dict with processing summary
    """
    from main import app, db
    from models import CaseFile, SkippedFile
    from bulk_import import scan_bulk_import_directory, BULK_IMPORT_DIR
    from upload_pipeline import (
        stage_bulk_upload,
        extract_zips_in_staging,
        build_file_queue,
        filter_zero_event_files,
        get_staging_path,
        clear_staging
    )
    from bulk_operations import queue_file_processing
    
    with app.app_context():
        try:
            logger.info(f"[BULK IMPORT] Starting bulk import for case {case_id}")
            
            # Update task state
            self.update_state(state='PROGRESS', meta={'stage': 'Scanning directory', 'progress': 0})
            
            # Step 1: Scan bulk import directory
            scan_result = scan_bulk_import_directory()
            
            if 'error' in scan_result:
                logger.error(f"[BULK IMPORT] Scan failed: {scan_result['error']}")
                return {'status': 'error', 'message': scan_result['error']}
            
            total_files = scan_result['total_supported']
            
            if total_files == 0:
                logger.info("[BULK IMPORT] No files found in directory")
                return {'status': 'success', 'message': 'No files to import', 'files_processed': 0}
            
            logger.info(f"[BULK IMPORT] Found {total_files} files to import")
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'stage': 'Staging files',
                'progress': 10,
                'files_found': total_files
            })
            
            # Step 2: Stage files from bulk import directory
            stage_result = stage_bulk_upload(
                case_id=case_id,
                source_folder=BULK_IMPORT_DIR,
                cleanup_after=True  # Move files to staging, delete originals
            )
            
            if stage_result['status'] != 'success':
                logger.error(f"[BULK IMPORT] Staging failed: {stage_result.get('message')}")
                return stage_result
            
            staging_dir = get_staging_path(case_id)
            files_staged = stage_result.get('files_staged', 0)
            
            logger.info(f"[BULK IMPORT] Staged {files_staged} files")
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'stage': 'Extracting ZIPs',
                'progress': 30,
                'files_staged': files_staged
            })
            
            # Step 3: Extract ZIPs (reuses nested extraction logic)
            extract_result = extract_zips_in_staging(case_id)
            
            if extract_result['status'] != 'success':
                logger.error(f"[BULK IMPORT] ZIP extraction failed: {extract_result.get('message')}")
            
            extracted_count = extract_result.get('total_extracted', 0)
            logger.info(f"[BULK IMPORT] Extracted {extracted_count} files from ZIPs")
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'stage': 'Building file queue',
                'progress': 50,
                'files_extracted': extracted_count
            })
            
            # Step 4: Build file queue (deduplication, 0-event detection)
            queue_result = build_file_queue(db, CaseFile, SkippedFile, case_id)
            
            if queue_result['status'] != 'success':
                logger.error(f"[BULK IMPORT] Queue build failed: {queue_result.get('message')}")
                clear_staging(case_id)
                return queue_result
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'stage': 'Filtering files',
                'progress': 70,
                'total_in_queue': len(queue_result['queue'])
            })
            
            # Step 5: Filter zero-event files
            filter_result = filter_zero_event_files(
                db, CaseFile, SkippedFile,
                queue_result['queue'],
                case_id
            )
            
            valid_count = filter_result['valid_files']
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'stage': 'Queueing for processing',
                'progress': 90,
                'valid_files': valid_count
            })
            
            # Step 6: Queue valid files for processing
            # Get CaseFile objects for the filtered queue
            if valid_count > 0:
                file_ids = [item[0] for item in filter_result['filtered_queue']]
                case_files = db.session.query(CaseFile).filter(CaseFile.id.in_(file_ids)).all()
                
                queue_file_processing(process_file, case_files, operation='full')
                logger.info(f"[BULK IMPORT] Queued {len(case_files)} files for processing")
            
            # Clean up staging
            clear_staging(case_id)
            
            # Final summary
            summary = {
                'status': 'success',
                'files_found': total_files,
                'files_staged': files_staged,
                'files_extracted': extracted_count,
                'duplicates_skipped': queue_result.get('duplicates_skipped', 0),
                'zero_event_files': filter_result['zero_events'],
                'valid_files': valid_count,
                'queued_for_processing': valid_count
            }
            
            logger.info(f"[BULK IMPORT] Complete: {summary}")
            
            return summary
            
        except Exception as e:
            logger.error(f"[BULK IMPORT] Fatal error: {e}", exc_info=True)
            # Try to clean up on error
            try:
                clear_staging(case_id)
            except:
                pass
            return {'status': 'error', 'message': str(e)}


# ============================================================================
# AI REPORT GENERATION
# ============================================================================

@celery_app.task(bind=True, name='tasks.generate_ai_report')
def generate_ai_report(self, report_id):
    """
    Generate AI report for a case using Ollama + Phi-3 14B
    
    Args:
        report_id: ID of the AIReport database record
        
    Returns:
        dict: Status and results
    """
    from main import app, db, opensearch_client
    from models import AIReport, Case, IOC
    from ai_report import generate_case_report_prompt, generate_report_with_ollama, format_report_title, markdown_to_html
    from datetime import datetime
    import time
    
    logger.info(f"[AI REPORT] Starting generation for report_id={report_id}")
    
    with app.app_context():
        try:
            # Get report record
            report = db.session.get(AIReport, report_id)
            if not report:
                logger.error(f"[AI REPORT] Report {report_id} not found")
                return {'status': 'error', 'message': 'Report not found'}
            
            # Store Celery task ID for cancellation support
            report.celery_task_id = self.request.id
            report.status = 'generating'
            report.current_stage = 'Initializing'
            report.progress_percent = 5
            report.progress_message = 'Initializing AI report generation...'
            db.session.commit()
            logger.info(f"[AI REPORT] Task ID: {self.request.id}")
            
            # Check for cancellation
            report = db.session.get(AIReport, report_id)
            if report.status == 'cancelled':
                logger.info(f"[AI REPORT] Report {report_id} was cancelled before starting")
                return {'status': 'cancelled', 'message': 'Report generation was cancelled'}
            
            # Get case data
            case = db.session.get(Case, report.case_id)
            if not case:
                report.status = 'failed'
                report.error_message = 'Case not found'
                db.session.commit()
                return {'status': 'error', 'message': 'Case not found'}
            
            logger.info(f"[AI REPORT] Gathering data for case '{case.name}'")
            
            # STAGE 1: Collecting Data
            report.current_stage = 'Collecting Data'
            report.progress_percent = 15
            report.progress_message = f'Collecting IOCs and tagged events for {case.name}...'
            db.session.commit()
            
            # Check for cancellation
            report = db.session.get(AIReport, report_id)
            if report.status == 'cancelled':
                logger.info(f"[AI REPORT] Report {report_id} was cancelled during data collection")
                return {'status': 'cancelled', 'message': 'Report generation was cancelled'}
            
            iocs = IOC.query.filter_by(case_id=case.id).all()
            logger.info(f"[AI REPORT] Found {len(iocs)} IOCs")
            
            # Get tagged events from OpenSearch (using TimelineTag table)
            # Limit to 50 events to prevent context window overflow (was 100)
            report.progress_percent = 30
            report.progress_message = 'Fetching top 50 tagged events from database...'
            db.session.commit()
            
            tagged_events = []
            try:
                # Get tagged event IDs from TimelineTag table (same as search page)
                from models import TimelineTag
                timeline_tags = TimelineTag.query.filter_by(case_id=case.id).order_by(TimelineTag.created_at.asc()).all()
                
                if timeline_tags:
                    logger.info(f"[AI REPORT] Found {len(timeline_tags)} tagged events in database")
                    
                    # Get event_ids for OpenSearch query
                    tagged_event_ids = [tag.event_id for tag in timeline_tags]
                    
                    # Fetch full event data from OpenSearch (limit to 50 to prevent context overflow)
                    if len(tagged_event_ids) > 0:
                        # Build index pattern
                        index_pattern = f"case_{case.id}_*"
                        
                        search_body = {
                            "query": {
                                "ids": {
                                    "values": tagged_event_ids[:50]  # Limit to 50 to prevent context overflow
                                }
                            },
                            "size": 50,
                            "sort": [{"timestamp": {"order": "asc", "unmapped_type": "date"}}]
                        }
                        
                        results = opensearch_client.search(
                            index=index_pattern,
                            body=search_body,
                            ignore_unavailable=True
                        )
                        
                        if results and 'hits' in results and 'hits' in results['hits']:
                            tagged_events = results['hits']['hits']
                            logger.info(f"[AI REPORT] Retrieved {len(tagged_events)} tagged events from OpenSearch")
                else:
                    logger.info(f"[AI REPORT] No tagged events found for case {case.id}")
                    
            except Exception as e:
                logger.warning(f"[AI REPORT] Error fetching tagged events: {e}")
                # Continue without tagged events
            
            # Check for cancellation before prompt building
            report = db.session.get(AIReport, report_id)
            if report.status == 'cancelled':
                logger.info(f"[AI REPORT] Report {report_id} was cancelled after data collection")
                return {'status': 'cancelled', 'message': 'Report generation was cancelled'}
            
            # STAGE 2: Analyzing Data
            report.current_stage = 'Analyzing Data'
            report.progress_percent = 40
            report.progress_message = f'Analyzing {len(iocs)} IOCs and {len(tagged_events)} tagged events...'
            db.session.commit()
            
            prompt = generate_case_report_prompt(case, iocs, tagged_events)
            logger.info(f"[AI REPORT] Prompt generated ({len(prompt)} characters)")
            
            # Store the prompt for debugging/review
            report.prompt_sent = prompt
            db.session.commit()
            
            # Check for cancellation before AI generation
            report = db.session.get(AIReport, report_id)
            if report.status == 'cancelled':
                logger.info(f"[AI REPORT] Report {report_id} was cancelled before AI generation")
                return {'status': 'cancelled', 'message': 'Report generation was cancelled'}
            
            # STAGE 3: Generating Report with AI
            report.current_stage = 'Generating Report'
            report.progress_percent = 50
            report.progress_message = f'Loading {report.model_name} model and generating report...'
            db.session.commit()
            
            start_time = time.time()
            # Use the model specified in the report record (from database settings)
            # Pass report object and db session for real-time streaming updates
            success, result = generate_report_with_ollama(
                prompt, 
                model=report.model_name,
                report_obj=report,
                db_session=db.session
            )
            generation_time = time.time() - start_time
            
            # Check for cancellation after AI generation
            report = db.session.get(AIReport, report_id)
            if report.status == 'cancelled':
                logger.info(f"[AI REPORT] Report {report_id} was cancelled after AI generation")
                return {'status': 'cancelled', 'message': 'Report generation was cancelled'}
            
            if success:
                # STAGE 4: Finalizing Report
                report.current_stage = 'Finalizing'
                report.progress_percent = 95
                report.progress_message = 'Converting report to HTML format...'
                db.session.commit()
                
                # Convert markdown report to HTML for Word compatibility
                markdown_report = result['report']
                html_report = markdown_to_html(markdown_report, case.name, case.company)
                
                # Update report with success
                report.status = 'completed'
                report.current_stage = 'Completed'
                report.report_title = format_report_title(case.name)
                report.report_content = html_report  # Store as HTML for Word compatibility
                report.raw_response = markdown_report  # Store raw markdown response for debugging
                report.generation_time_seconds = result['duration_seconds']
                report.completed_at = datetime.utcnow()
                report.model_name = result.get('model', 'phi3:14b')
                report.progress_percent = 100
                report.progress_message = 'Report completed successfully!'
                report.celery_task_id = None  # Clear task ID on completion
                
                # Store performance metrics
                eval_count = result.get('eval_count', 0)
                if eval_count > 0 and result['duration_seconds'] > 0:
                    report.tokens_per_second = eval_count / result['duration_seconds']
                    report.total_tokens = eval_count
                
                db.session.commit()
                
                logger.info(f"[AI REPORT] Report generated successfully in {generation_time:.1f}s")
                
                return {
                    'status': 'success',
                    'report_id': report_id,
                    'generation_time': generation_time,
                    'tokens_generated': result.get('eval_count', 0)
                }
            else:
                # Update report with failure
                error_msg = result.get('error', 'Unknown error')
                report.status = 'failed'
                report.current_stage = 'Failed'
                report.error_message = error_msg
                report.generation_time_seconds = generation_time
                report.celery_task_id = None  # Clear task ID on failure
                
                db.session.commit()
                
                logger.error(f"[AI REPORT] Generation failed: {error_msg}")
                
                return {
                    'status': 'error',
                    'report_id': report_id,
                    'message': error_msg
                }
                
        except Exception as e:
            logger.error(f"[AI REPORT] Fatal error: {e}", exc_info=True)
            
            # Try to update report status
            try:
                report = db.session.get(AIReport, report_id)
                if report:
                    report.status = 'failed'
                    report.error_message = str(e)
                    db.session.commit()
            except:
                pass
            
            return {
                'status': 'error',
                'report_id': report_id,
                'message': str(e)
            }
