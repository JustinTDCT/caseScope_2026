"""
Known User Utilities
Provides functions to check usernames against the Known Users database and IOCs
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def check_ioc_match(username: str, case_id: Optional[int] = None) -> Dict[str, any]:
    """
    Check if a username matches a USERNAME type IOC in the database
    
    Args:
        username: Username to check (case-insensitive)
        case_id: Optional case ID to filter IOCs (if None, checks all cases)
        
    Returns:
        Dict with:
            - 'is_ioc': bool (True if username matches a USERNAME type IOC)
            - 'threat_level': str ('low', 'medium', 'high', 'critical')
    """
    try:
        from models import IOC
        
        # Build query - only check active IOCs
        query = IOC.query.filter(
            IOC.ioc_type == 'username',
            IOC.ioc_value.ilike(username),
            IOC.is_active == True
        )
        
        # Filter by case if provided
        if case_id is not None:
            query = query.filter(IOC.case_id == case_id)
        
        # Get first matching IOC
        ioc = query.first()
        
        if ioc:
            return {
                'is_ioc': True,
                'threat_level': ioc.threat_level if hasattr(ioc, 'threat_level') else 'medium'
            }
        else:
            return {
                'is_ioc': False,
                'threat_level': None
            }
    
    except Exception as e:
        logger.error(f"[IOC_CHECK] Error checking username '{username}': {e}")
        return {
            'is_ioc': False,
            'threat_level': None
        }


def check_known_user(username: str) -> Dict[str, any]:
    """
    Check if a username exists in the Known Users database
    
    Args:
        username: Username to check (case-insensitive)
        
    Returns:
        Dict with:
            - 'is_known': bool (True if user exists in database)
            - 'compromised': bool (True if user is marked as compromised)
            - 'user_type': str ('domain', 'local', or '-')
    """
    try:
        from models import KnownUser
        
        # Case-insensitive lookup
        known_user = KnownUser.query.filter(
            KnownUser.username.ilike(username)
        ).first()
        
        if known_user:
            return {
                'is_known': True,
                'compromised': known_user.compromised,
                'user_type': known_user.user_type
            }
        else:
            return {
                'is_known': False,
                'compromised': False,
                'user_type': None
            }
    
    except Exception as e:
        logger.error(f"[KNOWN_USER_CHECK] Error checking username '{username}': {e}")
        return {
            'is_known': False,
            'compromised': False,
            'user_type': None
        }


def enrich_login_records(login_records: list, case_id: Optional[int] = None) -> list:
    """
    Enrich login records with Known User and IOC information
    
    Args:
        login_records: List of dicts with 'username' key
        case_id: Optional case ID for IOC filtering
        
    Returns:
        Same list with added keys:
            - 'is_known_user': bool
            - 'is_compromised': bool
            - 'user_type': str or None
            - 'is_ioc': bool
            - 'ioc_threat_level': str or None
    """
    try:
        enriched = []
        
        for record in login_records:
            username = record.get('username', '')
            
            # Check against Known Users database
            user_info = check_known_user(username)
            
            # Check against IOCs
            ioc_info = check_ioc_match(username, case_id)
            
            # Add enrichment data to record
            enriched_record = record.copy()
            enriched_record['is_known_user'] = user_info['is_known']
            enriched_record['is_compromised'] = user_info['compromised']
            enriched_record['user_type'] = user_info['user_type']
            enriched_record['is_ioc'] = ioc_info['is_ioc']
            enriched_record['ioc_threat_level'] = ioc_info['threat_level']
            
            enriched.append(enriched_record)
        
        # Log summary
        total = len(enriched)
        known = sum(1 for r in enriched if r['is_known_user'])
        compromised = sum(1 for r in enriched if r['is_compromised'])
        iocs = sum(1 for r in enriched if r['is_ioc'])
        
        logger.info(f"[KNOWN_USER_ENRICH] Enriched {total} records: {known} known users, {compromised} compromised, {iocs} IOCs")
        
        return enriched
    
    except Exception as e:
        logger.error(f"[KNOWN_USER_ENRICH] Error enriching records: {e}")
        # Return original records without enrichment on error
        return login_records

