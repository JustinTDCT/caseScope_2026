"""
Queue Cleanup Utility - Fix stuck and misclassified files

This module provides functions to:
1. Fix "Failed" files that are actually 0-event files (should be hidden)
2. Requeue "Queued" files that aren't in the Redis queue
3. Provide health check summary

Usage:
    from queue_cleanup import cleanup_queue
    result = cleanup_queue(db, case_id=None)  # All cases
    result = cleanup_queue(db, case_id=1)      # Specific case
"""

import logging
import redis
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def cleanup_queue(db, CaseFile, case_id: Optional[int] = None) -> Dict:
    """
    Clean up queue: fix failed files and requeue stuck files
    
    Args:
        db: SQLAlchemy database session
        CaseFile: CaseFile model class
        case_id: Optional case ID (None = all cases)
    
    Returns:
        dict: {
            'failed_fixed': int,           # Failed → Hidden
            'failed_fixed_files': List,    # File IDs fixed
            'queued_stuck': int,           # Queued but not in Redis
            'queued_requeued': int,        # Files requeued
            'queued_files': List,          # File IDs requeued
            'redis_queue_size': int,       # Current queue size
            'status': 'success' | 'error',
            'message': str
        }
    """
    result = {
        'failed_fixed': 0,
        'failed_fixed_files': [],
        'queued_stuck': 0,
        'queued_requeued': 0,
        'queued_files': [],
        'redis_queue_size': 0,
        'status': 'success',
        'message': ''
    }
    
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        result['redis_queue_size'] = r.llen('celery')
        
        # ============================================================================
        # STEP 1: Fix "Failed" files that are actually 0-event files
        # ============================================================================
        logger.info("="*80)
        logger.info("[QUEUE CLEANUP] Checking for misclassified failed files")
        logger.info("="*80)
        
        # Build base query
        failed_query = db.session.query(CaseFile).filter(
            CaseFile.is_deleted == False,
            ~CaseFile.indexing_status.in_(['Completed', 'Queued', 'Indexing', 'SIGMA Testing', 'IOC Hunting'])
        )
        
        # Add case filter if specified
        if case_id is not None:
            failed_query = failed_query.filter(CaseFile.case_id == case_id)
        
        failed_files = failed_query.all()
        
        logger.info(f"[QUEUE CLEANUP] Found {len(failed_files)} failed files")
        
        for file_obj in failed_files:
            # Check if it's a 0-event file or CyLR artifact
            if file_obj.event_count == 0:
                logger.info(f"[QUEUE CLEANUP] Fixing file {file_obj.id}: {file_obj.original_filename}")
                logger.info(f"[QUEUE CLEANUP]   Status: {file_obj.indexing_status} → Completed (Hidden)")
                
                file_obj.is_hidden = True
                file_obj.is_indexed = True
                file_obj.indexing_status = 'Completed'
                
                result['failed_fixed'] += 1
                result['failed_fixed_files'].append(file_obj.id)
            elif (file_obj.event_count == 1 and 
                  file_obj.file_type == 'JSON' and 
                  not file_obj.original_filename.lower().endswith('.evtx')):
                # CyLR artifact with 1 event
                logger.info(f"[QUEUE CLEANUP] Fixing CyLR artifact {file_obj.id}: {file_obj.original_filename}")
                logger.info(f"[QUEUE CLEANUP]   Status: {file_obj.indexing_status} → Completed (Hidden)")
                
                file_obj.is_hidden = True
                file_obj.is_indexed = True
                file_obj.indexing_status = 'Completed'
                
                result['failed_fixed'] += 1
                result['failed_fixed_files'].append(file_obj.id)
        
        # Commit failed file fixes
        if result['failed_fixed'] > 0:
            db.session.commit()
            logger.info(f"[QUEUE CLEANUP] ✓ Fixed {result['failed_fixed']} misclassified failed files")
        
        # ============================================================================
        # STEP 2: Requeue "Queued" files that aren't actually in Redis queue
        # ============================================================================
        logger.info("="*80)
        logger.info("[QUEUE CLEANUP] Checking for stuck queued files")
        logger.info("="*80)
        
        # Build base query
        queued_query = db.session.query(CaseFile).filter_by(
            indexing_status='Queued',
            is_deleted=False
        )
        
        # Add case filter if specified
        if case_id is not None:
            queued_query = queued_query.filter(CaseFile.case_id == case_id)
        
        queued_files = queued_query.all()
        
        result['queued_stuck'] = len(queued_files)
        logger.info(f"[QUEUE CLEANUP] Found {len(queued_files)} queued files")
        
        if len(queued_files) > 0 and result['redis_queue_size'] == 0:
            # Files are queued but Redis queue is empty - definitely stuck
            logger.warning(f"[QUEUE CLEANUP] Redis queue is empty but {len(queued_files)} files are 'Queued'")
            logger.info(f"[QUEUE CLEANUP] Requeuing files...")
            
            # Import here to avoid circular dependency
            from bulk_operations import queue_file_processing
            from tasks import process_file
            
            queued_count = queue_file_processing(process_file, queued_files, operation='full')
            
            result['queued_requeued'] = queued_count
            result['queued_files'] = [f.id for f in queued_files]
            result['redis_queue_size'] = r.llen('celery')  # Update after requeuing
            
            logger.info(f"[QUEUE CLEANUP] ✓ Requeued {queued_count} files")
        elif len(queued_files) > 0:
            logger.info(f"[QUEUE CLEANUP] ✓ {len(queued_files)} files queued, Redis has {result['redis_queue_size']} tasks - OK")
        else:
            logger.info(f"[QUEUE CLEANUP] ✓ No stuck files found")
        
        # Build summary message
        messages = []
        if result['failed_fixed'] > 0:
            messages.append(f"Fixed {result['failed_fixed']} misclassified failed files (now hidden)")
        if result['queued_requeued'] > 0:
            messages.append(f"Requeued {result['queued_requeued']} stuck files")
        if not messages:
            messages.append("No issues found - queue is healthy")
        
        result['message'] = ". ".join(messages)
        result['status'] = 'success'
        
        logger.info("="*80)
        logger.info(f"[QUEUE CLEANUP] Complete: {result['message']}")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"[QUEUE CLEANUP] Error: {e}", exc_info=True)
        result['status'] = 'error'
        result['message'] = f"Error: {str(e)}"
    
    return result


def get_queue_health(db, CaseFile, case_id: Optional[int] = None) -> Dict:
    """
    Get queue health status without making changes
    
    Args:
        db: SQLAlchemy database session
        CaseFile: CaseFile model class
        case_id: Optional case ID (None = all cases)
    
    Returns:
        dict: {
            'redis_queue_size': int,
            'files_queued': int,
            'files_failed': int,
            'files_processing': int,
            'misclassified_failed': int,  # Failed but have 0 events
            'stuck_queued': int,           # Queued but Redis empty
            'health_status': 'healthy' | 'warning' | 'error'
        }
    """
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        redis_queue_size = r.llen('celery')
        
        # Build base queries
        base_query = db.session.query(CaseFile).filter_by(is_deleted=False)
        if case_id is not None:
            base_query = base_query.filter(CaseFile.case_id == case_id)
        
        # Count files by status
        files_queued = base_query.filter_by(indexing_status='Queued').count()
        files_processing = base_query.filter(
            CaseFile.indexing_status.in_(['Indexing', 'SIGMA Testing', 'IOC Hunting'])
        ).count()
        files_failed = base_query.filter(
            ~CaseFile.indexing_status.in_(['Completed', 'Queued', 'Indexing', 'SIGMA Testing', 'IOC Hunting'])
        ).count()
        
        # Check for misclassified failed files (0-event files marked as failed)
        misclassified_query = base_query.filter(
            ~CaseFile.indexing_status.in_(['Completed', 'Queued', 'Indexing', 'SIGMA Testing', 'IOC Hunting']),
            CaseFile.event_count == 0
        )
        misclassified_failed = misclassified_query.count()
        
        # Check for stuck queued files (queued but Redis empty)
        stuck_queued = 0
        if files_queued > 0 and redis_queue_size == 0 and files_processing == 0:
            stuck_queued = files_queued
        
        # Determine health status
        if misclassified_failed > 0 or stuck_queued > 0:
            health_status = 'warning'
        elif files_failed > 0:
            health_status = 'warning'
        else:
            health_status = 'healthy'
        
        return {
            'redis_queue_size': redis_queue_size,
            'files_queued': files_queued,
            'files_failed': files_failed,
            'files_processing': files_processing,
            'misclassified_failed': misclassified_failed,
            'stuck_queued': stuck_queued,
            'health_status': health_status
        }
        
    except Exception as e:
        logger.error(f"[QUEUE HEALTH] Error: {e}", exc_info=True)
        return {
            'redis_queue_size': 0,
            'files_queued': 0,
            'files_failed': 0,
            'files_processing': 0,
            'misclassified_failed': 0,
            'stuck_queued': 0,
            'health_status': 'error'
        }

