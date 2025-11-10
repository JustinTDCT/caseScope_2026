"""
Login Analysis Module
Analyzes Windows logon events (Event ID 4624 and 4625) and provides distinct user/computer combinations
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Windows Logon Type mapping (for Event ID 4624/4625)
LOGON_TYPE_DESCRIPTIONS = {
    '0': 'System - Internal system account startup',
    '1': 'Special Logon - Privileged logon (Run as Administrator)',
    '2': 'Interactive (Console) - Physical keyboard/mouse login',
    '3': 'Network - Accessing shared resources (no RDP)',
    '4': 'Batch - Scheduled tasks',
    '5': 'Service - Windows service started',
    '6': 'Proxy - Legacy proxy logon (rare)',
    '7': 'Unlock - Workstation unlocked',
    '8': 'NetworkCleartext - Credentials in cleartext (bad)',
    '9': 'NewCredentials - RunAs with different credentials',
    '10': 'Remote Desktop (RDP) - Remote Desktop logon',
    '11': 'CachedInteractive - Cached domain credentials',
    '12': 'RemoteInteractive - Azure/WinRM/modern remote methods'
}


def get_logins_by_event_id(opensearch_client, case_id: int, event_id: str, 
                           date_range: str = 'all',
                           custom_date_start: Optional[datetime] = None,
                           custom_date_end: Optional[datetime] = None,
                           latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for specific Windows logon Event IDs
    Returns distinct username/computer combinations
    
    Args:
        opensearch_client: OpenSearch client instance
        case_id: Case ID to search within
        event_id: Event ID to search for (e.g., '4624', '4625')
        date_range: Time range ('all', '24h', '7d', '30d', 'custom')
        custom_date_start: Start datetime for custom range
        custom_date_end: End datetime for custom range
        latest_event_timestamp: Latest event timestamp for relative ranges
        
    Returns:
        Dict with 'logins' list and 'total_events' count
    """
    try:
        index_pattern = f"case_{case_id}_*"
        
        # Build date filter
        date_filter = None
        if date_range == 'custom' and custom_date_start and custom_date_end:
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": custom_date_start.isoformat(),
                        "lte": custom_date_end.isoformat()
                    }
                }
            }
        elif date_range in ['24h', '7d', '30d'] and latest_event_timestamp:
            hours_map = {'24h': 24, '7d': 168, '30d': 720}
            hours = hours_map.get(date_range, 0)
            from datetime import timedelta
            start_time = latest_event_timestamp - timedelta(hours=hours)
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": start_time.isoformat()
                    }
                }
            }
        
        # Build OpenSearch query for specified Event ID
        # Check multiple possible field locations
        event_id_int = int(event_id)
        must_conditions = [
            {
                "bool": {
                    "should": [
                        {"term": {"normalized_event_id": event_id}},
                        {"term": {"System.EventID": event_id_int}},
                        {"term": {"System.EventID.#text": event_id}},
                        {"term": {"Event.System.EventID": event_id_int}},
                        {"term": {"Event.System.EventID.#text": event_id}}
                    ],
                    "minimum_should_match": 1
                }
            }
        ]
        
        if date_filter:
            must_conditions.append(date_filter)
        
        query = {
            "size": 10000,  # Max results to process
            "_source": [
                "normalized_timestamp",
                "normalized_event_id",
                "normalized_computer_name",
                "System.Computer",
                "System.EventID",
                "Event.System.Computer",
                "Event.System.EventID",
                "Event.EventData.TargetUserName",
                "Event.EventData.SubjectUserName",
                "Event.EventData.LogonType",
                "EventData.TargetUserName",
                "EventData.SubjectUserName",
                "EventData.LogonType"
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "sort": [{"normalized_timestamp": {"order": "desc"}}]
        }
        
        logger.info(f"[LOGIN_ANALYSIS] Searching for Event ID {event_id} in case {case_id}")
        result = opensearch_client.search(index=index_pattern, body=query)
        
        total_events = result['hits']['total']['value']
        logger.info(f"[LOGIN_ANALYSIS] Found {total_events} Event ID {event_id} events")
        
        # Process results to extract distinct username/computer pairs
        seen_combinations = set()  # (username, computer) tuples
        distinct_logins = []
        
        for hit in result['hits']['hits']:
            source = hit['_source']
            
            # Extract computer name
            computer = _extract_computer_name(source)
            
            # Extract username (TargetUserName is the logged-in user)
            username = _extract_username(source)
            
            # Extract LogonType for 4624 events
            logon_type = _extract_logon_type(source)
            
            if username and computer:
                # Create unique key (include logon_type for better deduplication)
                combo_key = (username.lower(), computer.lower(), logon_type)
                
                # Only add if this combination hasn't been seen
                if combo_key not in seen_combinations:
                    seen_combinations.add(combo_key)
                    
                    # Get timestamp
                    timestamp = source.get('normalized_timestamp', 'Unknown')
                    if timestamp != 'Unknown':
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            pass
                    
                    # Get LogonType description
                    logon_type_desc = LOGON_TYPE_DESCRIPTIONS.get(logon_type, f'{logon_type} - Unknown')
                    
                    distinct_logins.append({
                        'username': username,
                        'computer': computer,
                        'first_seen': timestamp,
                        'logon_type': logon_type,
                        'logon_type_description': logon_type_desc
                    })
        
        logger.info(f"[LOGIN_ANALYSIS] Found {len(distinct_logins)} distinct username/computer combinations")
        
        # Enrich with Known User and IOC data
        from known_user_utils import enrich_login_records
        enriched_logins = enrich_login_records(distinct_logins, case_id)
        
        return {
            'success': True,
            'logins': enriched_logins,
            'total_events': total_events,
            'distinct_count': len(enriched_logins)
        }
        
    except Exception as e:
        logger.error(f"[LOGIN_ANALYSIS] Error analyzing logins: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'logins': [],
            'total_events': 0,
            'distinct_count': 0
        }


def get_successful_logins(opensearch_client, case_id: int, date_range: str = 'all',
                          custom_date_start: Optional[datetime] = None,
                          custom_date_end: Optional[datetime] = None,
                          latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for Event ID 4624 (successful Windows logons)
    Returns distinct username/computer combinations
    """
    return get_logins_by_event_id(
        opensearch_client, case_id, '4624', date_range,
        custom_date_start, custom_date_end, latest_event_timestamp
    )


def get_failed_logins(opensearch_client, case_id: int, date_range: str = 'all',
                      custom_date_start: Optional[datetime] = None,
                      custom_date_end: Optional[datetime] = None,
                      latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for Event ID 4625 (failed Windows logons)
    Returns distinct username/computer combinations
    """
    return get_logins_by_event_id(
        opensearch_client, case_id, '4625', date_range,
        custom_date_start, custom_date_end, latest_event_timestamp
    )


def get_console_logins(opensearch_client, case_id: int, date_range: str = 'all',
                       custom_date_start: Optional[datetime] = None,
                       custom_date_end: Optional[datetime] = None,
                       latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for Event ID 4624 with LogonType = 2 (interactive console logins)
    Returns distinct username/computer combinations
    """
    try:
        index_pattern = f"case_{case_id}_*"
        
        # Build date filter (same logic as other login functions)
        date_filter = None
        if date_range == 'custom' and custom_date_start and custom_date_end:
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": custom_date_start.isoformat(),
                        "lte": custom_date_end.isoformat()
                    }
                }
            }
        elif date_range in ['24h', '7d', '30d'] and latest_event_timestamp:
            hours_map = {'24h': 24, '7d': 168, '30d': 720}
            hours = hours_map.get(date_range, 0)
            from datetime import timedelta
            start_time = latest_event_timestamp - timedelta(hours=hours)
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": start_time.isoformat()
                    }
                }
            }
        
        # Build OpenSearch query for Event ID 4624 AND LogonType = 2
        must_conditions = [
            # Event ID 4624
            {
                "bool": {
                    "should": [
                        {"term": {"normalized_event_id": "4624"}},
                        {"term": {"System.EventID": 4624}},
                        {"term": {"System.EventID.#text": "4624"}},
                        {"term": {"Event.System.EventID": 4624}},
                        {"term": {"Event.System.EventID.#text": "4624"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            # LogonType = 2
            {
                "bool": {
                    "should": [
                        {"term": {"Event.EventData.LogonType": 2}},
                        {"term": {"Event.EventData.LogonType": "2"}},
                        {"term": {"Event.EventData.LogonType.#text": "2"}},
                        {"term": {"EventData.LogonType": 2}},
                        {"term": {"EventData.LogonType": "2"}}
                    ],
                    "minimum_should_match": 1
                }
            }
        ]
        
        if date_filter:
            must_conditions.append(date_filter)
        
        query = {
            "size": 10000,  # Max results to process
            "_source": [
                "normalized_timestamp",
                "normalized_event_id",
                "normalized_computer_name",
                "System.Computer",
                "System.EventID",
                "Event.System.Computer",
                "Event.System.EventID",
                "Event.EventData.TargetUserName",
                "Event.EventData.SubjectUserName",
                "Event.EventData.LogonType",
                "EventData.TargetUserName",
                "EventData.SubjectUserName",
                "EventData.LogonType"
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "sort": [{"normalized_timestamp": {"order": "desc"}}]
        }
        
        logger.info(f"[CONSOLE_LOGINS] Searching for Event ID 4624 with LogonType=2 in case {case_id}")
        result = opensearch_client.search(index=index_pattern, body=query)
        
        total_events = result['hits']['total']['value']
        logger.info(f"[CONSOLE_LOGINS] Found {total_events} Event ID 4624 LogonType=2 events")
        
        # Process results to extract distinct username/computer pairs
        seen_combinations = set()  # (username, computer) tuples
        distinct_logins = []
        
        for hit in result['hits']['hits']:
            source = hit['_source']
            
            # Extract computer name (same as other login functions)
            computer = _extract_computer_name(source)
            
            # Extract username (TargetUserName)
            username = _extract_username(source)
            
            if username and computer:
                # Create unique key
                combo_key = (username.lower(), computer.lower())
                
                # Only add if this combination hasn't been seen
                if combo_key not in seen_combinations:
                    seen_combinations.add(combo_key)
                    
                    # Get timestamp
                    timestamp = source.get('normalized_timestamp', 'Unknown')
                    if timestamp != 'Unknown':
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            pass
                    
                    distinct_logins.append({
                        'username': username,
                        'computer': computer,
                        'first_seen': timestamp
                    })
        
        logger.info(f"[CONSOLE_LOGINS] Found {len(distinct_logins)} distinct console login username/computer combinations")
        
        # Enrich with Known User and IOC data
        from known_user_utils import enrich_login_records
        enriched_logins = enrich_login_records(distinct_logins, case_id)
        
        return {
            'success': True,
            'logins': enriched_logins,
            'total_events': total_events,
            'distinct_count': len(enriched_logins)
        }
        
    except Exception as e:
        logger.error(f"[CONSOLE_LOGINS] Error analyzing console logins: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'logins': [],
            'total_events': 0,
            'distinct_count': 0
        }


def get_rdp_connections(opensearch_client, case_id: int, date_range: str = 'all',
                        custom_date_start: Optional[datetime] = None,
                        custom_date_end: Optional[datetime] = None,
                        latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for Event ID 1149 (RDP connections - TerminalServices-RemoteConnectionManager)
    Returns distinct username/computer combinations
    
    Note: Uses different field for username (Event.UserData.EventXML.Param1)
    """
    try:
        index_pattern = f"case_{case_id}_*"
        
        # Build date filter (same logic as other login functions)
        date_filter = None
        if date_range == 'custom' and custom_date_start and custom_date_end:
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": custom_date_start.isoformat(),
                        "lte": custom_date_end.isoformat()
                    }
                }
            }
        elif date_range in ['24h', '7d', '30d'] and latest_event_timestamp:
            hours_map = {'24h': 24, '7d': 168, '30d': 720}
            hours = hours_map.get(date_range, 0)
            from datetime import timedelta
            start_time = latest_event_timestamp - timedelta(hours=hours)
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": start_time.isoformat()
                    }
                }
            }
        
        # Build OpenSearch query for Event ID 1149
        event_id = '1149'
        event_id_int = 1149
        must_conditions = [
            {
                "bool": {
                    "should": [
                        {"term": {"normalized_event_id": event_id}},
                        {"term": {"System.EventID": event_id_int}},
                        {"term": {"System.EventID.#text": event_id}},
                        {"term": {"Event.System.EventID": event_id_int}},
                        {"term": {"Event.System.EventID.#text": event_id}}
                    ],
                    "minimum_should_match": 1
                }
            }
        ]
        
        if date_filter:
            must_conditions.append(date_filter)
        
        query = {
            "size": 10000,  # Max results to process
            "_source": [
                "normalized_timestamp",
                "normalized_event_id",
                "normalized_computer_name",
                "System.Computer",
                "System.EventID",
                "Event.System.Computer",
                "Event.System.EventID",
                "Event.UserData.EventXML.Param1",  # RDP username field
                "UserData.EventXML.Param1"
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "sort": [{"normalized_timestamp": {"order": "desc"}}]
        }
        
        logger.info(f"[RDP_ANALYSIS] Searching for Event ID 1149 in case {case_id}")
        result = opensearch_client.search(index=index_pattern, body=query)
        
        total_events = result['hits']['total']['value']
        logger.info(f"[RDP_ANALYSIS] Found {total_events} Event ID 1149 events")
        
        # Process results to extract distinct username/computer pairs
        seen_combinations = set()  # (username, computer) tuples
        distinct_connections = []
        
        for hit in result['hits']['hits']:
            source = hit['_source']
            
            # Extract computer name (same as other login functions)
            computer = _extract_computer_name(source)
            
            # Extract RDP username from Event.UserData.EventXML.Param1
            username = _extract_rdp_username(source)
            
            if username and computer:
                # Create unique key
                combo_key = (username.lower(), computer.lower())
                
                # Only add if this combination hasn't been seen
                if combo_key not in seen_combinations:
                    seen_combinations.add(combo_key)
                    
                    # Get timestamp
                    timestamp = source.get('normalized_timestamp', 'Unknown')
                    if timestamp != 'Unknown':
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            pass
                    
                    distinct_connections.append({
                        'username': username,
                        'computer': computer,
                        'first_seen': timestamp
                    })
        
        logger.info(f"[RDP_ANALYSIS] Found {len(distinct_connections)} distinct RDP username/computer combinations")
        
        # Enrich with Known User and IOC data
        from known_user_utils import enrich_login_records
        enriched_connections = enrich_login_records(distinct_connections, case_id)
        
        return {
            'success': True,
            'logins': enriched_connections,
            'total_events': total_events,
            'distinct_count': len(enriched_connections)
        }
        
    except Exception as e:
        logger.error(f"[RDP_ANALYSIS] Error analyzing RDP connections: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'logins': [],
            'total_events': 0,
            'distinct_count': 0
        }


def _extract_computer_name(source: Dict) -> Optional[str]:
    """Extract computer name from event source (handles multiple field locations)"""
    # Try normalized field first
    if 'normalized_computer_name' in source and source['normalized_computer_name']:
        return source['normalized_computer_name']
    
    # Try System.Computer
    if 'System' in source and isinstance(source['System'], dict):
        computer = source['System'].get('Computer')
        if computer:
            return computer
    
    # Try Event.System.Computer
    if 'Event' in source and isinstance(source['Event'], dict):
        if 'System' in source['Event'] and isinstance(source['Event']['System'], dict):
            computer = source['Event']['System'].get('Computer')
            if computer:
                return computer
    
    return None


def _extract_username(source: Dict) -> Optional[str]:
    """Extract username from event source (TargetUserName is the logged-in user)"""
    # Try Event.EventData.TargetUserName (most common for EVTX->JSON)
    if 'Event' in source and isinstance(source['Event'], dict):
        if 'EventData' in source['Event'] and isinstance(source['Event']['EventData'], dict):
            username = source['Event']['EventData'].get('TargetUserName')
            if username and _is_valid_username(username):
                return username
    
    # Try EventData.TargetUserName (direct structure)
    if 'EventData' in source and isinstance(source['EventData'], dict):
        username = source['EventData'].get('TargetUserName')
        if username and _is_valid_username(username):
            return username
    
    # Fallback to SubjectUserName if TargetUserName not found
    if 'Event' in source and isinstance(source['Event'], dict):
        if 'EventData' in source['Event'] and isinstance(source['Event']['EventData'], dict):
            username = source['Event']['EventData'].get('SubjectUserName')
            if username and _is_valid_username(username):
                return username
    
    if 'EventData' in source and isinstance(source['EventData'], dict):
        username = source['EventData'].get('SubjectUserName')
        if username and _is_valid_username(username):
            return username
    
    return None


def _extract_rdp_username(source: Dict) -> Optional[str]:
    """Extract RDP username from Event ID 1149 (Event.UserData.EventXML.Param1)"""
    # Try Event.UserData.EventXML.Param1 (RDP connection username)
    if 'Event' in source and isinstance(source['Event'], dict):
        if 'UserData' in source['Event'] and isinstance(source['Event']['UserData'], dict):
            if 'EventXML' in source['Event']['UserData'] and isinstance(source['Event']['UserData']['EventXML'], dict):
                username = source['Event']['UserData']['EventXML'].get('Param1')
                if username and _is_valid_username(username):
                    return username
    
    # Try UserData.EventXML.Param1 (direct structure)
    if 'UserData' in source and isinstance(source['UserData'], dict):
        if 'EventXML' in source['UserData'] and isinstance(source['UserData']['EventXML'], dict):
            username = source['UserData']['EventXML'].get('Param1')
            if username and _is_valid_username(username):
                return username
    
    return None


def _is_valid_username(username: str) -> bool:
    """
    Check if username is valid (not a system account or special account)
    
    Filters out:
    - System accounts: SYSTEM, ANONYMOUS LOGON, etc.
    - Machine accounts: accounts ending with $
    - Windows system accounts: DWM-*, UMFD-*
    """
    if not username:
        return False
    
    # Filter out explicit system accounts
    if username in ['-', 'SYSTEM', 'ANONYMOUS LOGON', '$']:
        return False
    
    # Filter out machine accounts (ending with $)
    if username.endswith('$'):
        return False
    
    # Filter out Desktop Window Manager accounts (DWM-*)
    if username.upper().startswith('DWM-'):
        return False
    
    # Filter out User Mode Font Driver accounts (UMFD-*)
    if username.upper().startswith('UMFD-'):
        return False
    
    return True


def get_vpn_authentications(opensearch_client, case_id: int, firewall_ip: str,
                            date_range: str = 'all',
                            custom_date_start: Optional[datetime] = None,
                            custom_date_end: Optional[datetime] = None,
                            latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for VPN authentications (Event ID 4624 with specific firewall IP)
    Returns ALL events (NO deduplication) - every authentication attempt
    
    Args:
        opensearch_client: OpenSearch client instance
        case_id: Case ID to search within
        firewall_ip: IP address of the firewall to filter by
        date_range: Time range ('all', '24h', '7d', '30d', 'custom')
        custom_date_start: Start datetime for custom range
        custom_date_end: End datetime for custom range
        latest_event_timestamp: Latest event timestamp for relative ranges
        
    Returns:
        Dict with 'authentications' list (ALL events, no deduplication)
    """
    try:
        index_pattern = f"case_{case_id}_*"
        
        # Build date filter
        date_filter = None
        if date_range == 'custom' and custom_date_start and custom_date_end:
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": custom_date_start.isoformat(),
                        "lte": custom_date_end.isoformat()
                    }
                }
            }
        elif date_range in ['24h', '7d', '30d'] and latest_event_timestamp:
            hours_map = {'24h': 24, '7d': 168, '30d': 720}
            hours = hours_map.get(date_range, 0)
            from datetime import timedelta
            start_time = latest_event_timestamp - timedelta(hours=hours)
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": start_time.isoformat()
                    }
                }
            }
        
        # Build OpenSearch query for Event ID 4624 with firewall IP filter
        event_id = '4624'
        event_id_int = 4624
        must_conditions = [
            # Event ID 4624
            {
                "bool": {
                    "should": [
                        {"term": {"normalized_event_id": event_id}},
                        {"term": {"System.EventID": event_id_int}},
                        {"term": {"System.EventID.#text": event_id}},
                        {"term": {"Event.System.EventID": event_id_int}},
                        {"term": {"Event.System.EventID.#text": event_id}}
                    ],
                    "minimum_should_match": 1
                }
            },
            # IP Address matches firewall
            {
                "bool": {
                    "should": [
                        {"term": {"Event.EventData.IpAddress.keyword": firewall_ip}},
                        {"term": {"EventData.IpAddress.keyword": firewall_ip}},
                        {"term": {"IpAddress.keyword": firewall_ip}}
                    ],
                    "minimum_should_match": 1
                }
            }
        ]
        
        if date_filter:
            must_conditions.append(date_filter)
        
        query = {
            "size": 10000,  # Max results to process
            "_source": [
                "normalized_timestamp",
                "normalized_event_id",
                "Event.EventData.TargetUserName",
                "Event.EventData.WorkstationName",
                "Event.EventData.IpAddress",
                "EventData.TargetUserName",
                "EventData.WorkstationName",
                "EventData.IpAddress"
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "sort": [{"normalized_timestamp": {"order": "desc"}}]
        }
        
        logger.info(f"[VPN_AUTHS] Searching for Event ID 4624 with IP {firewall_ip} in case {case_id}")
        result = opensearch_client.search(index=index_pattern, body=query)
        
        total_events = result['hits']['total']['value']
        logger.info(f"[VPN_AUTHS] Found {total_events} VPN authentication events")
        
        # Process ALL results (NO deduplication)
        authentications = []
        
        for hit in result['hits']['hits']:
            source = hit['_source']
            
            # Extract username from Event.EventData.TargetUserName
            username = None
            if 'Event' in source and 'EventData' in source['Event'] and 'TargetUserName' in source['Event']['EventData']:
                username = source['Event']['EventData']['TargetUserName']
            elif 'EventData' in source and 'TargetUserName' in source['EventData']:
                username = source['EventData']['TargetUserName']
            
            # Extract workstation name from Event.EventData.WorkstationName
            workstation_name = None
            if 'Event' in source and 'EventData' in source['Event'] and 'WorkstationName' in source['Event']['EventData']:
                workstation_name = source['Event']['EventData']['WorkstationName']
            elif 'EventData' in source and 'WorkstationName' in source['EventData']:
                workstation_name = source['EventData']['WorkstationName']
            
            # Get timestamp
            timestamp = source.get('normalized_timestamp', 'N/A')
            
            # Get event ID and index for linking to event details
            event_id = hit.get('_id')
            event_index = hit.get('_index')
            
            # Add ALL events (no filtering, no deduplication)
            if username:
                authentications.append({
                    'username': username,
                    'workstation_name': workstation_name or 'N/A',
                    'timestamp': timestamp,
                    'event_id': event_id,
                    'event_index': event_index
                })
        
        logger.info(f"[VPN_AUTHS] Returning {len(authentications)} VPN authentication events")
        
        # Enrich with Known User and IOC data
        from known_user_utils import enrich_login_records
        enriched_auths = enrich_login_records(authentications, case_id)
        
        return {
            'success': True,
            'authentications': enriched_auths
        }
    
    except Exception as e:
        logger.error(f"[VPN_AUTHS] Error analyzing VPN authentications: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'authentications': []
        }


def _extract_logon_type(source: Dict) -> str:
    """Extract LogonType from Event ID 4624 event"""
    # Try Event.EventData.LogonType (most common for EVTX->JSON)
    if 'Event' in source and isinstance(source['Event'], dict):
        if 'EventData' in source['Event'] and isinstance(source['Event']['EventData'], dict):
            logon_type = source['Event']['EventData'].get('LogonType')
            if logon_type:
                return str(logon_type)
    
    # Try EventData.LogonType (direct structure)
    if 'EventData' in source and isinstance(source['EventData'], dict):
        logon_type = source['EventData'].get('LogonType')
        if logon_type:
            return str(logon_type)
    
    return 'Unknown'


def get_failed_vpn_attempts(opensearch_client, case_id: int, firewall_ip: str,
                            date_range: str = 'all',
                            custom_date_start: Optional[datetime] = None,
                            custom_date_end: Optional[datetime] = None,
                            latest_event_timestamp: Optional[datetime] = None) -> Dict:
    """
    Query OpenSearch for failed VPN attempts (Event ID 4625 with specific firewall IP)
    Returns ALL events (NO deduplication) - every failed authentication attempt
    
    Args:
        opensearch_client: OpenSearch client instance
        case_id: Case ID to search within
        firewall_ip: IP address of the firewall to filter by
        date_range: Time range ('all', '24h', '7d', '30d', 'custom')
        custom_date_start: Start datetime for custom range
        custom_date_end: End datetime for custom range
        latest_event_timestamp: Latest event timestamp for relative ranges
        
    Returns:
        Dict with 'attempts' list (ALL events, no deduplication)
    """
    try:
        index_pattern = f"case_{case_id}_*"
        
        # Build date filter
        date_filter = None
        if date_range == 'custom' and custom_date_start and custom_date_end:
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": custom_date_start.isoformat(),
                        "lte": custom_date_end.isoformat()
                    }
                }
            }
        elif date_range in ['24h', '7d', '30d'] and latest_event_timestamp:
            hours_map = {'24h': 24, '7d': 168, '30d': 720}
            hours = hours_map.get(date_range, 0)
            from datetime import timedelta
            start_time = latest_event_timestamp - timedelta(hours=hours)
            date_filter = {
                "range": {
                    "normalized_timestamp": {
                        "gte": start_time.isoformat()
                    }
                }
            }
        
        # Build OpenSearch query for Event ID 4625 with firewall IP filter
        event_id = '4625'
        event_id_int = 4625
        must_conditions = [
            # Event ID 4625 (failed logon)
            {
                "bool": {
                    "should": [
                        {"term": {"normalized_event_id": event_id}},
                        {"term": {"System.EventID": event_id_int}},
                        {"term": {"System.EventID.#text": event_id}},
                        {"term": {"Event.System.EventID": event_id_int}},
                        {"term": {"Event.System.EventID.#text": event_id}}
                    ],
                    "minimum_should_match": 1
                }
            },
            # IP Address matches firewall
            {
                "bool": {
                    "should": [
                        {"term": {"Event.EventData.IpAddress.keyword": firewall_ip}},
                        {"term": {"EventData.IpAddress.keyword": firewall_ip}},
                        {"term": {"IpAddress.keyword": firewall_ip}}
                    ],
                    "minimum_should_match": 1
                }
            }
        ]
        
        if date_filter:
            must_conditions.append(date_filter)
        
        query = {
            "size": 10000,  # Max results to process
            "_source": [
                "normalized_timestamp",
                "normalized_event_id",
                "Event.EventData.TargetUserName",
                "Event.EventData.WorkstationName",
                "Event.EventData.IpAddress",
                "EventData.TargetUserName",
                "EventData.WorkstationName",
                "EventData.IpAddress"
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "sort": [{"normalized_timestamp": {"order": "desc"}}]
        }
        
        logger.info(f"[FAILED_VPN] Searching for Event ID 4625 with IP {firewall_ip} in case {case_id}")
        result = opensearch_client.search(index=index_pattern, body=query)
        
        total_events = result['hits']['total']['value']
        logger.info(f"[FAILED_VPN] Found {total_events} failed VPN attempt events")
        
        # Process ALL results (NO deduplication)
        attempts = []
        
        for hit in result['hits']['hits']:
            source = hit['_source']
            
            # Extract username from Event.EventData.TargetUserName
            username = None
            if 'Event' in source and 'EventData' in source['Event'] and 'TargetUserName' in source['Event']['EventData']:
                username = source['Event']['EventData']['TargetUserName']
            elif 'EventData' in source and 'TargetUserName' in source['EventData']:
                username = source['EventData']['TargetUserName']
            
            # Extract workstation name from Event.EventData.WorkstationName
            workstation_name = None
            if 'Event' in source and 'EventData' in source['Event'] and 'WorkstationName' in source['Event']['EventData']:
                workstation_name = source['Event']['EventData']['WorkstationName']
            elif 'EventData' in source and 'WorkstationName' in source['EventData']:
                workstation_name = source['EventData']['WorkstationName']
            
            # Get timestamp
            timestamp = source.get('normalized_timestamp', 'N/A')
            
            # Get event ID and index for linking to event details
            event_id = hit.get('_id')
            event_index = hit.get('_index')
            
            # Add ALL events (no filtering, no deduplication)
            if username:
                attempts.append({
                    'username': username,
                    'workstation_name': workstation_name or 'N/A',
                    'timestamp': timestamp,
                    'event_id': event_id,
                    'event_index': event_index
                })
        
        logger.info(f"[FAILED_VPN] Returning {len(attempts)} failed VPN attempt events")
        
        # Enrich with Known User and IOC data
        from known_user_utils import enrich_login_records
        enriched_attempts = enrich_login_records(attempts, case_id)
        
        return {
            'success': True,
            'attempts': enriched_attempts
        }
    
    except Exception as e:
        logger.error(f"[FAILED_VPN] Error analyzing failed VPN attempts: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'attempts': []
        }
