"""
Hidden Files Management Module
Handles viewing and toggling visibility of 0-event files
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_hidden_files_count(db_session, case_id: int) -> int:
    """Get count of hidden files for a case"""
    from models import CaseFile
    
    return db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=True
    ).count()


def get_hidden_files(db_session, case_id: int, page: int = 1, per_page: int = 50):
    """Get paginated list of hidden files"""
    from models import CaseFile
    
    query = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=True
    ).order_by(CaseFile.uploaded_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination


def toggle_file_visibility(db_session, file_id: int, user_id: int) -> Dict:
    """Toggle a file's hidden status"""
    from models import CaseFile
    
    file = db_session.get(CaseFile, file_id)
    
    if not file:
        return {'success': False, 'error': 'File not found'}
    
    file.is_hidden = not file.is_hidden
    action = 'hidden' if file.is_hidden else 'visible'
    
    try:
        db_session.commit()
        logger.info(f"[HIDDEN] User {user_id} set file {file_id} to {action}")
        return {
            'success': True,
            'is_hidden': file.is_hidden,
            'action': action
        }
    except Exception as e:
        db_session.rollback()
        logger.error(f"[HIDDEN] Failed to toggle file {file_id}: {e}")
        return {'success': False, 'error': str(e)}


def bulk_unhide_files(db_session, case_id: int, file_ids: List[int], user_id: int) -> Dict:
    """Unhide multiple files at once"""
    from models import CaseFile
    
    try:
        files = db_session.query(CaseFile).filter(
            CaseFile.id.in_(file_ids),
            CaseFile.case_id == case_id,
            CaseFile.is_deleted == False
        ).all()
        
        count = 0
        for file in files:
            file.is_hidden = False
            count += 1
        
        db_session.commit()
        logger.info(f"[HIDDEN] User {user_id} unhid {count} files in case {case_id}")
        
        return {'success': True, 'count': count}
    except Exception as e:
        db_session.rollback()
        logger.error(f"[HIDDEN] Bulk unhide failed: {e}")
        return {'success': False, 'error': str(e)}


def get_file_stats_with_hidden(db_session, case_id: int) -> Dict:
    """Get file statistics including hidden count"""
    from models import CaseFile
    from sqlalchemy import func
    
    # Total files (excluding deleted)
    total_files = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False
    ).count()
    
    # Hidden files
    hidden_files = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=True
    ).count()
    
    # Visible files
    visible_files = total_files - hidden_files
    
    # Total space (all files including hidden)
    total_space_bytes = db_session.query(func.sum(CaseFile.file_size)).filter_by(
        case_id=case_id,
        is_deleted=False
    ).scalar() or 0
    
    # Total events (visible files only)
    total_events = db_session.query(func.sum(CaseFile.event_count)).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False
    ).scalar() or 0
    
    # SIGMA events (visible files only) - using violation_count (active field)
    sigma_events = db_session.query(func.sum(CaseFile.violation_count)).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False
    ).scalar() or 0
    
    # IOC events (visible files only)
    ioc_events = db_session.query(func.sum(CaseFile.ioc_event_count)).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False
    ).scalar() or 0
    
    # Processing state counts (visible files only)
    files_indexing = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False,
        indexing_status='Indexing'
    ).count()
    
    files_sigma = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False,
        indexing_status='SIGMA Testing'
    ).count()
    
    files_ioc_hunting = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False,
        indexing_status='IOC Hunting'
    ).count()
    
    files_completed = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False,
        indexing_status='Completed'
    ).count()
    
    files_queued = db_session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False,
        indexing_status='Queued'
    ).count()
    
    # Failed files (any status that's not a known state)
    known_statuses = ['Completed', 'Indexing', 'SIGMA Testing', 'IOC Hunting', 'Queued']
    files_failed = db_session.query(CaseFile).filter(
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False,
        CaseFile.is_hidden == False,
        ~CaseFile.indexing_status.in_(known_statuses)
    ).count()
    
    return {
        'total_files': total_files,
        'visible_files': visible_files,
        'hidden_files': hidden_files,
        'total_space_bytes': total_space_bytes,
        'total_events': total_events,
        'sigma_events': sigma_events,
        'ioc_events': ioc_events,
        'files_completed': files_completed,
        'files_indexing': files_indexing,
        'files_sigma': files_sigma,
        'files_ioc_hunting': files_ioc_hunting,
        'files_queued': files_queued,
        'files_failed': files_failed
    }

