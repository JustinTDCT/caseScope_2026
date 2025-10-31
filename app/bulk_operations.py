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
    
    deleted_count = 0
    for f in files:
        if f.opensearch_key:
            try:
                index_name = make_index_name(case_id, f.original_filename)
                opensearch_client.indices.delete(index=index_name, ignore=[404])
                logger.info(f"[BULK OPS] Deleted OpenSearch index: {index_name}")
                deleted_count += 1
            except Exception as e:
                logger.warning(f"[BULK OPS] Could not delete index for file {f.id}: {e}")
    
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
            
            # Clear has_ioc flag for all events in this index
            update_body = {
                "script": {
                    "source": "ctx._source.remove('has_ioc')",
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


def queue_file_processing(process_file_task, files: List[Any], operation: str = 'full'):
    """
    Queue file processing tasks for multiple files
    
    Args:
        process_file_task: Celery task (process_file)
        files: List of CaseFile objects
        operation: Operation type ('full', 'sigma', 'ioc')
    
    Returns:
        Number of tasks queued
    """
    for f in files:
        process_file_task.delay(f.id, operation=operation)
        logger.debug(f"[BULK OPS] Queued {operation} processing for file {f.id}")
    
    logger.info(f"[BULK OPS] Queued {operation} processing for {len(files)} file(s)")
    return len(files)

