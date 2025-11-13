"""
Global Bulk Operations Module (v1.13.7)
Reusable functions for bulk file operations across ALL cases

Similar to bulk_operations.py but operates globally (all cases) instead of single case.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_all_files(db, include_deleted: bool = False, include_hidden: bool = True) -> List[Any]:
    """
    Get all files across ALL cases
    
    Args:
        db: Database session
        include_deleted: Include soft-deleted files
        include_hidden: Include hidden (0-event) files
        
    Returns:
        List of CaseFile objects
    """
    from models import CaseFile
    
    query = db.session.query(CaseFile)
    
    if not include_deleted:
        query = query.filter(CaseFile.is_deleted == False)
    
    if not include_hidden:
        query = query.filter(CaseFile.is_hidden == False)
    
    files = query.all()
    logger.info(f"[GLOBAL BULK] Retrieved {len(files)} files across all cases")
    return files


def get_selected_files_global(db, file_ids: List[int]) -> List[Any]:
    """
    Get specific files by ID (can be from multiple cases)
    
    Args:
        db: Database session
        file_ids: List of file IDs
        
    Returns:
        List of CaseFile objects
    """
    from models import CaseFile
    
    files = db.session.query(CaseFile).filter(
        CaseFile.id.in_(file_ids),
        CaseFile.is_deleted == False
    ).all()
    
    logger.info(f"[GLOBAL BULK] Retrieved {len(files)} selected files (from {file_ids} IDs)")
    return files


def requeue_failed_files_global(db) -> int:
    """
    Requeue all failed files across ALL cases
    
    Args:
        db: Database session
        
    Returns:
        Number of files requeued
    """
    from models import CaseFile
    
    # Get failed files (any status not in known good statuses)
    known_statuses = ['Completed', 'Indexing', 'SIGMA Testing', 'IOC Hunting', 'Queued']
    failed_files = db.session.query(CaseFile).filter(
        CaseFile.is_deleted == False,
        CaseFile.is_hidden == False,
        ~CaseFile.indexing_status.in_(known_statuses)
    ).all()
    
    count = 0
    for f in failed_files:
        f.indexing_status = 'Queued'
        f.celery_task_id = None
        f.error_message = None
        count += 1
    
    db.session.commit()
    logger.info(f"[GLOBAL BULK] Requeued {count} failed files")
    return count


def queue_files_for_processing_global(process_file_task, files: List[Any], operation: str, db_session) -> int:
    """
    Queue files for processing (global version)
    
    Args:
        process_file_task: Celery task function (process_file)
        files: List of CaseFile objects
        operation: 'full', 'sigma_only', or 'ioc_only'
        db_session: Database session
        
    Returns:
        Number of files queued
    """
    from bulk_operations import queue_file_processing
    
    # Reuse existing queue_file_processing logic
    queued = queue_file_processing(process_file_task, files, operation, db_session)
    
    logger.info(f"[GLOBAL BULK] Queued {queued} files for {operation} processing")
    return queued


def clear_global_opensearch_events(opensearch_client, files: List[Any]) -> int:
    """
    Clear OpenSearch events for files (can span multiple cases)
    
    Args:
        opensearch_client: OpenSearch client
        files: List of CaseFile objects
        
    Returns:
        Number of events deleted
    """
    from utils import make_index_name
    
    # Group files by case_id for efficient deletion
    files_by_case = {}
    for f in files:
        if f.case_id not in files_by_case:
            files_by_case[f.case_id] = []
        files_by_case[f.case_id].append(f)
    
    total_deleted = 0
    
    for case_id, case_files in files_by_case.items():
        index_name = make_index_name(case_id)
        
        for f in case_files:
            if f.opensearch_key:
                try:
                    result = opensearch_client.delete_by_query(
                        index=index_name,
                        body={"query": {"term": {"file_id": f.id}}},
                        conflicts='proceed',
                        ignore=[404]
                    )
                    event_count = result.get('deleted', 0) if isinstance(result, dict) else 0
                    total_deleted += event_count
                except Exception as e:
                    logger.warning(f"[GLOBAL BULK] Could not delete events for file {f.id}: {e}")
    
    logger.info(f"[GLOBAL BULK] Deleted {total_deleted} events across {len(files_by_case)} cases")
    return total_deleted


def clear_global_sigma_violations(db, file_ids: Optional[List[int]] = None) -> int:
    """
    Clear SIGMA violations globally (all cases or specific files)
    
    Args:
        db: Database session
        file_ids: Optional list of specific file IDs
        
    Returns:
        Number of violations deleted
    """
    from models import SigmaViolation
    
    query = db.session.query(SigmaViolation)
    
    if file_ids:
        query = query.filter(SigmaViolation.case_file_id.in_(file_ids))
    
    count = query.delete(synchronize_session=False)
    db.session.commit()
    
    logger.info(f"[GLOBAL BULK] Cleared {count} SIGMA violations")
    return count


def clear_global_ioc_matches(db, file_ids: Optional[List[int]] = None) -> int:
    """
    Clear IOC matches globally (all cases or specific files)
    
    Args:
        db: Database session
        file_ids: Optional list of specific file IDs
        
    Returns:
        Number of IOC matches deleted
    """
    from models import IOCMatch
    
    query = db.session.query(IOCMatch)
    
    if file_ids:
        query = query.filter(IOCMatch.case_file_id.in_(file_ids))
    
    count = query.delete(synchronize_session=False)
    db.session.commit()
    
    logger.info(f"[GLOBAL BULK] Cleared {count} IOC matches")
    return count


def clear_global_ioc_flags_in_opensearch(opensearch_client, files: List[Any]) -> int:
    """
    Clear has_ioc flags from OpenSearch events (can span multiple cases)
    
    Args:
        opensearch_client: OpenSearch client
        files: List of CaseFile objects
        
    Returns:
        Number of events updated
    """
    from utils import make_index_name
    
    # Group files by case_id
    files_by_case = {}
    for f in files:
        if f.case_id not in files_by_case:
            files_by_case[f.case_id] = []
        files_by_case[f.case_id].append(f)
    
    total_updated = 0
    
    for case_id, case_files in files_by_case.items():
        index_name = make_index_name(case_id)
        
        try:
            # Check if index exists
            if not opensearch_client.indices.exists(index=index_name):
                continue
            
            # Build query for all files in this case
            file_ids = [f.id for f in case_files if f.opensearch_key]
            
            if not file_ids:
                continue
            
            # Update has_ioc flag for all files at once
            result = opensearch_client.update_by_query(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"terms": {"file_id": file_ids}},
                                {"exists": {"field": "has_ioc"}}
                            ]
                        }
                    },
                    "script": {
                        "source": "ctx._source.remove('has_ioc')",
                        "lang": "painless"
                    }
                },
                conflicts='proceed',
                wait_for_completion=True,
                refresh=True,
                ignore=[404]
            )
            
            updated = result.get('updated', 0) if isinstance(result, dict) else 0
            total_updated += updated
            
        except Exception as e:
            logger.warning(f"[GLOBAL BULK] Could not clear IOC flags for case {case_id}: {e}")
    
    logger.info(f"[GLOBAL BULK] Cleared IOC flags from {total_updated} events across {len(files_by_case)} cases")
    return total_updated


def prepare_files_for_reindex_global(db, files: List[Any]) -> int:
    """
    Prepare files for re-indexing (reset status, clear data)
    
    Args:
        db: Database session
        files: List of CaseFile objects
        
    Returns:
        Number of files prepared
    """
    for f in files:
        f.indexing_status = 'Queued'
        f.celery_task_id = None
        f.error_message = None
        f.is_indexed = False
        f.event_count = 0
        f.violation_count = 0
        f.ioc_event_count = 0
    
    db.session.commit()
    logger.info(f"[GLOBAL BULK] Prepared {len(files)} files for re-indexing")
    return len(files)


def prepare_files_for_rechainsaw_global(db, files: List[Any]) -> int:
    """
    Prepare files for re-SIGMA (reset SIGMA data only)
    
    Args:
        db: Database session
        files: List of CaseFile objects
        
    Returns:
        Number of files prepared
    """
    for f in files:
        f.indexing_status = 'Queued'
        f.celery_task_id = None
        f.violation_count = 0
    
    db.session.commit()
    logger.info(f"[GLOBAL BULK] Prepared {len(files)} files for re-SIGMA")
    return len(files)


def prepare_files_for_rehunt_global(db, files: List[Any]) -> int:
    """
    Prepare files for IOC re-hunting (reset IOC data only)
    
    Args:
        db: Database session
        files: List of CaseFile objects
        
    Returns:
        Number of files prepared
    """
    for f in files:
        f.indexing_status = 'Queued'
        f.celery_task_id = None
        f.ioc_event_count = 0
    
    db.session.commit()
    logger.info(f"[GLOBAL BULK] Prepared {len(files)} files for IOC re-hunting")
    return len(files)


def delete_files_globally(db, opensearch_client, files: List[Any]) -> Dict[str, int]:
    """
    Delete files and all associated data (across multiple cases)
    
    Args:
        db: Database session
        opensearch_client: OpenSearch client
        files: List of CaseFile objects
        
    Returns:
        Dict with deletion counts
    """
    import os
    from utils import make_index_name
    
    stats = {
        'files_deleted': 0,
        'events_deleted': 0,
        'sigma_deleted': 0,
        'ioc_deleted': 0,
        'disk_deleted': 0
    }
    
    # Group files by case for efficient OpenSearch deletion
    files_by_case = {}
    for f in files:
        if f.case_id not in files_by_case:
            files_by_case[f.case_id] = []
        files_by_case[f.case_id].append(f)
    
    # Delete from OpenSearch
    for case_id, case_files in files_by_case.items():
        index_name = make_index_name(case_id)
        
        for f in case_files:
            if f.opensearch_key:
                try:
                    result = opensearch_client.delete_by_query(
                        index=index_name,
                        body={"query": {"term": {"file_id": f.id}}},
                        conflicts='proceed',
                        ignore=[404]
                    )
                    stats['events_deleted'] += result.get('deleted', 0) if isinstance(result, dict) else 0
                except Exception as e:
                    logger.warning(f"[GLOBAL BULK] Could not delete OpenSearch events for file {f.id}: {e}")
    
    # Delete SIGMA violations and IOC matches
    from models import SigmaViolation, IOCMatch
    
    file_ids = [f.id for f in files]
    
    stats['sigma_deleted'] = db.session.query(SigmaViolation).filter(
        SigmaViolation.case_file_id.in_(file_ids)
    ).delete(synchronize_session=False)
    
    stats['ioc_deleted'] = db.session.query(IOCMatch).filter(
        IOCMatch.case_file_id.in_(file_ids)
    ).delete(synchronize_session=False)
    
    # Delete from filesystem and database
    for f in files:
        # Delete from filesystem
        file_path = f.file_path if hasattr(f, 'file_path') else None
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                stats['disk_deleted'] += 1
            except Exception as e:
                logger.warning(f"[GLOBAL BULK] Could not delete file from disk: {e}")
        
        # Delete from database
        db.session.delete(f)
        stats['files_deleted'] += 1
    
    db.session.commit()
    
    logger.info(f"[GLOBAL BULK] Deleted {stats['files_deleted']} files, {stats['events_deleted']} events, "
                f"{stats['sigma_deleted']} SIGMA violations, {stats['ioc_deleted']} IOC matches")
    
    return stats

