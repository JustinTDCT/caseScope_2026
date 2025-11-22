"""
Known User ↔ IOC Integration Module
Version: 1.21.0
Date: November 22, 2025

PURPOSE:
Automatically synchronize Known Users and IOCs to maintain consistency:
- When a Known User is marked as compromised → Create username IOC
- When a username IOC is created → Create Known User entry (if doesn't exist)

This ensures analysts don't have to manually manage both systems separately.
"""

from models import KnownUser, IOC
from main import db
import logging

logger = logging.getLogger('app')


def sync_user_to_ioc(case_id, username, user_id, current_user_id, description=None):
    """
    Create IOC when user is marked as compromised
    
    Args:
        case_id: Case ID
        username: Username to create IOC for
        user_id: KnownUser ID (for logging/reference)
        current_user_id: CaseScope user performing the action
        description: Optional description for the IOC
    
    Returns:
        (success: bool, ioc_id: int or None, message: str)
    """
    try:
        # Check if IOC already exists
        existing_ioc = IOC.query.filter_by(
            case_id=case_id,
            ioc_type='username',
            ioc_value=username
        ).first()
        
        if existing_ioc:
            logger.info(f"[KNOWN USER → IOC] IOC already exists for username '{username}' (IOC ID: {existing_ioc.id})")
            return (True, existing_ioc.id, 'IOC already exists')
        
        # Create new IOC
        ioc = IOC(
            case_id=case_id,
            ioc_type='username',
            ioc_value=username,
            description=description or f'Auto-created from compromised Known User (ID: {user_id})',
            threat_level='high',  # Compromised users are high threat
            is_active=True,
            created_by=current_user_id
        )
        
        db.session.add(ioc)
        db.session.commit()
        
        logger.info(f"[KNOWN USER → IOC] Created IOC (ID: {ioc.id}) for compromised user '{username}' (Known User ID: {user_id})")
        return (True, ioc.id, 'IOC created successfully')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[KNOWN USER → IOC] Failed to create IOC for username '{username}': {e}")
        return (False, None, str(e))


def sync_ioc_to_user(case_id, username, ioc_id, current_user_id, threat_level='medium'):
    """
    Create Known User when username IOC is added
    
    Args:
        case_id: Case ID
        username: Username from IOC
        ioc_id: IOC ID (for logging/reference)
        current_user_id: CaseScope user performing the action
        threat_level: IOC threat level (used to set compromised status)
    
    Returns:
        (success: bool, user_id: int or None, message: str)
    """
    try:
        # Check if Known User already exists (case-insensitive)
        existing_user = KnownUser.query.filter(
            KnownUser.case_id == case_id,
            db.func.lower(KnownUser.username) == username.lower()
        ).first()
        
        if existing_user:
            # User exists - update compromised status if needed
            if threat_level in ['high', 'critical'] and not existing_user.compromised:
                existing_user.compromised = True
                db.session.commit()
                logger.info(f"[IOC → KNOWN USER] Updated user '{username}' (ID: {existing_user.id}) to compromised (from IOC ID: {ioc_id})")
                return (True, existing_user.id, 'Known User updated to compromised')
            else:
                logger.info(f"[IOC → KNOWN USER] Known User already exists for username '{username}' (ID: {existing_user.id})")
                return (True, existing_user.id, 'Known User already exists')
        
        # Create new Known User
        # Type is 'unknown' since we don't know if domain/local/invalid from just the IOC
        # User can manually update the type later
        known_user = KnownUser(
            case_id=case_id,
            username=username,
            user_type='unknown',  # v1.21.0: Don't assume domain/local without evidence
            user_sid=None,  # No SID from IOC alone
            compromised=(threat_level in ['high', 'critical']),  # Auto-flag if high/critical threat
            active=True,  # Assume active unless evidence otherwise
            added_method='ioc_sync',  # v1.21.0: Track that this came from IOC
            added_by=current_user_id
        )
        
        db.session.add(known_user)
        db.session.commit()
        
        logger.info(f"[IOC → KNOWN USER] Created Known User (ID: {known_user.id}) for username IOC '{username}' (IOC ID: {ioc_id})")
        return (True, known_user.id, 'Known User created successfully')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[IOC → KNOWN USER] Failed to create Known User for username '{username}': {e}")
        return (False, None, str(e))


def unsync_user_from_ioc(case_id, username, user_id):
    """
    Remove IOC when user is unmarked as compromised
    
    Args:
        case_id: Case ID
        username: Username to remove IOC for
        user_id: KnownUser ID (for logging)
    
    Returns:
        (success: bool, message: str)
    
    Note: This is OPTIONAL behavior. Some orgs may want to keep the IOC even if user 
    is unmarked as compromised. This function is provided but not automatically called.
    """
    try:
        ioc = IOC.query.filter_by(
            case_id=case_id,
            ioc_type='username',
            ioc_value=username
        ).first()
        
        if not ioc:
            return (True, 'No IOC found to remove')
        
        # Check if IOC was auto-created by this system
        if 'Auto-created from compromised Known User' in (ioc.description or ''):
            db.session.delete(ioc)
            db.session.commit()
            logger.info(f"[KNOWN USER ← IOC] Removed auto-created IOC (ID: {ioc.id}) for user '{username}' (Known User ID: {user_id})")
            return (True, 'IOC removed successfully')
        else:
            # IOC was manually created, don't auto-delete it
            logger.info(f"[KNOWN USER ← IOC] IOC (ID: {ioc.id}) for '{username}' was manually created, not auto-removing")
            return (True, 'IOC was manually created, preserved')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[KNOWN USER ← IOC] Failed to remove IOC for username '{username}': {e}")
        return (False, str(e))


def get_sync_status(case_id, username):
    """
    Get synchronization status between Known User and IOC
    
    Returns:
        {
            'has_known_user': bool,
            'has_ioc': bool,
            'known_user_id': int or None,
            'ioc_id': int or None,
            'known_user_compromised': bool or None,
            'ioc_active': bool or None,
            'in_sync': bool
        }
    """
    known_user = KnownUser.query.filter(
        KnownUser.case_id == case_id,
        db.func.lower(KnownUser.username) == username.lower()
    ).first()
    
    ioc = IOC.query.filter_by(
        case_id=case_id,
        ioc_type='username',
        ioc_value=username
    ).first()
    
    has_user = known_user is not None
    has_ioc = ioc is not None
    
    # "In sync" means: if user is compromised, IOC exists; if IOC exists, user is compromised
    in_sync = True
    if has_user and known_user.compromised and not has_ioc:
        in_sync = False  # Compromised user but no IOC
    if has_ioc and ioc.is_active and (not has_user or not known_user.compromised):
        in_sync = False  # Active IOC but user not marked compromised
    
    return {
        'has_known_user': has_user,
        'has_ioc': has_ioc,
        'known_user_id': known_user.id if has_user else None,
        'ioc_id': ioc.id if has_ioc else None,
        'known_user_compromised': known_user.compromised if has_user else None,
        'ioc_active': ioc.is_active if has_ioc else None,
        'in_sync': in_sync
    }

