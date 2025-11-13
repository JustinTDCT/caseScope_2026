"""
Bulk Operations Module
Reusable functions for bulk file operations (reindex, rechainsaw, rehunt)
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def clear_case_opensearch_indices(opensearch_client, case_id: int, files: List[Any]) -> int:
    """
    Clear all OpenSearch indices for a case's files
    
    Args:
        opensearch_client: OpenSearch client instance
        case_id: Case ID
        files: List of CaseFile objects
    
    Returns:
        Number of indices deleted
    """
    from utils import make_index_name
    
    # v1.13.1: Delete events by file_id (not entire index - it's shared by all files in case)
    index_name = make_index_name(case_id)  # Gets case index
    deleted_count = 0
    
    for f in files:
        if f.opensearch_key:
            try:
                # Delete events for this file only
                result = opensearch_client.delete_by_query(
                    index=index_name,
                    body={"query": {"term": {"file_id": f.id}}},
                    conflicts='proceed',
                    ignore=[404]
                )
                event_count = result.get('deleted', 0) if isinstance(result, dict) else 0
                logger.info(f"[BULK OPS] Deleted {event_count} events for file {f.id}")
                deleted_count += 1
            except Exception as e:
                logger.warning(f"[BULK OPS] Could not delete events for file {f.id}: {e}")
    
    return deleted_count


def clear_case_sigma_violations(db, case_id: int) -> int:
    """
    Clear all SIGMA violations for a case
    
    Args:
        db: Database session
        case_id: Case ID
    
    Returns:
        Number of violations deleted
    """
    from models import SigmaViolation
    
    count = db.session.query(SigmaViolation).filter_by(case_id=case_id).delete()
    logger.info(f"[BULK OPS] Cleared {count} SIGMA violations for case {case_id}")
    return count


def clear_case_ioc_matches(db, case_id: int) -> int:
    """
    Clear all IOC matches for a case
    
    Args:
        db: Database session
        case_id: Case ID
    
    Returns:
        Number of IOC matches deleted
    """
    from models import IOCMatch
    
    count = db.session.query(IOCMatch).filter_by(case_id=case_id).delete()
    logger.info(f"[BULK OPS] Cleared {count} IOC matches for case {case_id}")
    return count


def clear_case_ioc_flags_in_opensearch(opensearch_client, case_id: int, files: list) -> int:
    """
    Clear has_ioc flags from all OpenSearch indices for a case
    This ensures old IOC flags are removed before re-hunting
    
    Args:
        opensearch_client: OpenSearch client
        case_id: Case ID
        files: List of CaseFile objects
    
    Returns:
        Number of events updated
    """
    total_updated = 0
    
    for case_file in files:
        if not case_file.is_indexed or not case_file.opensearch_key:
            continue
        
        # Generate index name from opensearch_key
        # opensearch_key format: "case2_ATN76254_filename" or "case2_log_..."
        # Need to remove the "case2_" prefix and convert to lowercase
        # IMPORTANT: Also convert spaces to underscores (matches make_index_name logic)
        opensearch_key_clean = case_file.opensearch_key
        if opensearch_key_clean.lower().startswith(f'case{case_id}_'):
            opensearch_key_clean = opensearch_key_clean[len(f'case{case_id}_'):]
        
        index_name = opensearch_key_clean.lower().replace('%4', '4').replace(' ', '_')
        index_name = f"case_{case_id}_{index_name}"
        
        try:
            # Check if index exists
            if not opensearch_client.indices.exists(index=index_name):
                continue
            
            # Clear has_ioc flag and ioc_count for all events in this index
            update_body = {
                "script": {
                    "source": "ctx._source.remove('has_ioc'); ctx._source.remove('ioc_count')",
                    "lang": "painless"
                },
                "query": {
                    "term": {"has_ioc": True}
                }
            }
            
            response = opensearch_client.update_by_query(
                index=index_name,
                body=update_body,
                conflicts='proceed'
            )
            
            updated = response.get('updated', 0)
            total_updated += updated
            
            if updated > 0:
                logger.info(f"[BULK OPS] Cleared has_ioc flags from {updated} events in {index_name}")
        
        except Exception as e:
            logger.warning(f"[BULK OPS] Could not clear has_ioc flags in {index_name}: {e}")
            continue
    
    logger.info(f"[BULK OPS] ✓ Cleared has_ioc flags from {total_updated} total events across all indices")
    return total_updated


def clear_file_sigma_violations(db, file_id: int) -> int:
    """
    Clear SIGMA violations for a specific file
    
    Args:
        db: Database session
        file_id: File ID
    
    Returns:
        Number of violations deleted
    """
    from models import SigmaViolation
    
    count = db.session.query(SigmaViolation).filter_by(file_id=file_id).delete()
    logger.info(f"[BULK OPS] Cleared {count} SIGMA violations for file {file_id}")
    return count


def clear_case_sigma_flags_in_opensearch(opensearch_client, case_id: int, files: list) -> int:
    """
    Clear has_sigma flags and sigma_rule fields from all OpenSearch indices for a case
    This ensures old SIGMA flags are removed before re-running SIGMA detection
    
    Args:
        opensearch_client: OpenSearch client
        case_id: Case ID
        files: List of CaseFile objects
    
    Returns:
        Number of events updated
    """
    total_updated = 0
    
    for case_file in files:
        if not case_file.is_indexed or not case_file.opensearch_key:
            continue
        
        # Generate index name from opensearch_key
        # opensearch_key format: "case2_ATN76254_filename" or "case2_log_..."
        # Need to remove the "case2_" prefix and convert to lowercase
        # IMPORTANT: Also convert spaces to underscores (matches make_index_name logic)
        opensearch_key_clean = case_file.opensearch_key
        if opensearch_key_clean.lower().startswith(f'case{case_id}_'):
            opensearch_key_clean = opensearch_key_clean[len(f'case{case_id}_'):]
        
        index_name = opensearch_key_clean.lower().replace('%4', '4').replace(' ', '_')
        index_name = f"case_{case_id}_{index_name}"
        
        try:
            # Check if index exists
            if not opensearch_client.indices.exists(index=index_name):
                continue
            
            # Clear has_sigma flag and sigma_rule field for all events in this index
            update_body = {
                "script": {
                    "source": "ctx._source.remove('has_sigma'); ctx._source.remove('sigma_rule')",
                    "lang": "painless"
                },
                "query": {
                    "term": {"has_sigma": True}
                }
            }
            
            response = opensearch_client.update_by_query(
                index=index_name,
                body=update_body,
                conflicts='proceed'
            )
            
            updated = response.get('updated', 0)
            total_updated += updated
            
            if updated > 0:
                logger.info(f"[BULK OPS] Cleared has_sigma flags from {updated} events in {index_name}")
        
        except Exception as e:
            logger.warning(f"[BULK OPS] Could not clear has_sigma flags in {index_name}: {e}")
            continue
    
    logger.info(f"[BULK OPS] ✓ Cleared has_sigma flags from {total_updated} total events across all indices")
    return total_updated


def clear_file_sigma_flags_in_opensearch(opensearch_client, case_id: int, file_obj) -> int:
    """
    Clear has_sigma flags and sigma_rule fields from OpenSearch index for a specific file
    This ensures old SIGMA flags are removed before re-running SIGMA detection
    
    Args:
        opensearch_client: OpenSearch client
        case_id: Case ID
        file_obj: CaseFile object
    
    Returns:
        Number of events updated
    """
    if not file_obj.is_indexed or not file_obj.opensearch_key:
        return 0
    
    # Generate index name from opensearch_key
    opensearch_key_clean = file_obj.opensearch_key
    if opensearch_key_clean.lower().startswith(f'case{case_id}_'):
        opensearch_key_clean = opensearch_key_clean[len(f'case{case_id}_'):]
    
    index_name = opensearch_key_clean.lower().replace('%4', '4').replace(' ', '_')
    index_name = f"case_{case_id}_{index_name}"
    
    try:
        # Check if index exists
        if not opensearch_client.indices.exists(index=index_name):
            return 0
        
        # Clear has_sigma flag and sigma_rule field for all events in this index
        update_body = {
            "script": {
                "source": "ctx._source.remove('has_sigma'); ctx._source.remove('sigma_rule')",
                "lang": "painless"
            },
            "query": {
                "term": {"has_sigma": True}
            }
        }
        
        response = opensearch_client.update_by_query(
            index=index_name,
            body=update_body,
            conflicts='proceed'
        )
        
        updated = response.get('updated', 0)
        
        if updated > 0:
            logger.info(f"[BULK OPS] Cleared has_sigma flags from {updated} events in {index_name}")
        
        return updated
    
    except Exception as e:
        logger.warning(f"[BULK OPS] Could not clear has_sigma flags in {index_name}: {e}")
        return 0


def clear_file_ioc_matches(db, file_id: int) -> int:
    """
    Clear IOC matches for a specific file
    
    Args:
        db: Database session
        file_id: File ID
    
    Returns:
        Number of IOC matches deleted
    """
    from models import IOCMatch
    
    count = db.session.query(IOCMatch).filter_by(file_id=file_id).delete()
    logger.info(f"[BULK OPS] Cleared {count} IOC matches for file {file_id}")
    return count


def clear_case_timeline_tags(db, case_id: int) -> int:
    """
    Clear all timeline tags for a case
    Timeline tags reference event_id and index_name which change during reindex
    
    Args:
        db: Database session
        case_id: Case ID
    
    Returns:
        Number of tags deleted
    """
    from models import TimelineTag
    
    count = db.session.query(TimelineTag).filter_by(case_id=case_id).delete()
    logger.info(f"[BULK OPS] Cleared {count} timeline tag(s) for case {case_id}")
    return count


def reset_file_metadata(file_obj: Any, reset_opensearch_key: bool = True):
    """
    Reset file processing metadata
    
    Args:
        file_obj: CaseFile object
        reset_opensearch_key: Whether to clear opensearch_key (True for reindex, False for rechainsaw/rehunt)
    """
    file_obj.event_count = 0
    file_obj.violation_count = 0
    file_obj.ioc_event_count = 0
    file_obj.is_indexed = False
    file_obj.indexing_status = 'Queued'  # Reset status to Queued for reprocessing
    
    if reset_opensearch_key:
        file_obj.opensearch_key = None
    
    logger.debug(f"[BULK OPS] Reset metadata for file {file_obj.id} (opensearch_key cleared: {reset_opensearch_key}, status set to Queued)")


def get_case_files(db, case_id: int, include_deleted: bool = False, include_hidden: bool = False) -> List[Any]:
    """
    Get all files for a case
    
    Args:
        db: Database session
        case_id: Case ID
        include_deleted: Whether to include deleted files
        include_hidden: Whether to include hidden files (0-event/CyLR artifacts)
    
    Returns:
        List of CaseFile objects
    """
    from models import CaseFile
    
    query = db.session.query(CaseFile).filter_by(case_id=case_id)
    
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    
    if not include_hidden:
        query = query.filter_by(is_hidden=False)
    
    files = query.all()
    logger.info(f"[BULK OPS] Found {len(files)} file(s) for case {case_id} (include_hidden={include_hidden})")
    return files


def queue_file_processing(process_file_task, files: List[Any], operation: str = 'full', db_session=None):
    """
    Queue file processing tasks for multiple files
    
    Args:
        process_file_task: Celery task (process_file)
        files: List of CaseFile objects
        operation: Operation type ('full', 'chainsaw_only', 'ioc_only')
        db_session: Optional database session (if None, will not commit)
    
    Returns:
        Number of tasks queued
    """
    queued_count = 0
    skipped_count = 0
    errors = []
    
    for f in files:
        # CRITICAL: Prevent duplicate queuing for 'full' operation
        # Skip files that are already indexed (unless they've been reset for re-index)
        # Re-index operations call reset_file_metadata() first, which sets is_indexed=False
        if operation == 'full' and f.is_indexed:
            logger.debug(f"[BULK OPS] Skipping file {f.id} (already indexed, use re-index to re-process)")
            skipped_count += 1
            continue
        
        # CRITICAL: Check for stale task_id before queuing
        if f.celery_task_id:
            from celery.result import AsyncResult
            from celery_app import celery_app
            old_task = AsyncResult(f.celery_task_id, app=celery_app)
            
            # If old task is still active, skip this file
            if old_task.state in ['PENDING', 'STARTED', 'RETRY']:
                logger.debug(f"[BULK OPS] Skipping file {f.id} (already queued: {f.celery_task_id}, state: {old_task.state})")
                skipped_count += 1
                continue
            else:
                # Old task is finished, clear it and continue
                logger.debug(f"[BULK OPS] File {f.id} has stale task_id {f.celery_task_id} (state: {old_task.state}), clearing before requeue")
                f.celery_task_id = None
        
        try:
            result = process_file_task.delay(f.id, operation=operation)
            # Store task ID in database for tracking
            if hasattr(f, 'celery_task_id'):
                f.celery_task_id = result.id
            logger.debug(f"[BULK OPS] Queued {operation} processing for file {f.id} (task_id: {result.id})")
            queued_count += 1
        except Exception as e:
            error_msg = f"Failed to queue file {f.id}: {e}"
            logger.error(f"[BULK OPS] {error_msg}")
            errors.append(error_msg)
            # CRITICAL: Clear task_id if queuing failed
            if hasattr(f, 'celery_task_id'):
                f.celery_task_id = None
            # Continue with other files even if one fails
    
    # CRITICAL: Commit the task_id changes to database
    if db_session and queued_count > 0:
        try:
            db_session.commit()
            logger.debug(f"[BULK OPS] Committed {queued_count} task_id assignments to database")
        except Exception as e:
            logger.error(f"[BULK OPS] Failed to commit task_ids: {e}")
            db_session.rollback()
    
    if errors:
        logger.warning(f"[BULK OPS] Queued {queued_count}/{len(files)} files successfully. {len(errors)} errors occurred, {skipped_count} skipped.")
        for error in errors[:10]:  # Log first 10 errors
            logger.warning(f"[BULK OPS]   - {error}")
    else:
        if skipped_count > 0:
            logger.info(f"[BULK OPS] Successfully queued {operation} processing for {queued_count} file(s), skipped {skipped_count} already-indexed/queued files")
        else:
            logger.info(f"[BULK OPS] Successfully queued {operation} processing for {queued_count} file(s)")
    
    return queued_count

