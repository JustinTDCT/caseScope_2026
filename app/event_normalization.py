"""
Event Normalization Module
Normalize event fields during ingestion for consistent search/display
"""

from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def normalize_event_timestamp(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract and normalize timestamp from various event structures
    
    Returns ISO 8601 timestamp string or None
    """
    timestamp_value = None
    
    # Priority 1: EVTX structure - System.TimeCreated.#attributes.SystemTime or @attributes.SystemTime
    if 'System' in event:
        time_created = event.get('System', {}).get('TimeCreated', {})
        timestamp_value = time_created.get('#attributes', {}).get('SystemTime') or time_created.get('@attributes', {}).get('SystemTime')
    
    # Priority 2: EVTX->JSON import - Event.System.TimeCreated
    if not timestamp_value and 'Event' in event and isinstance(event.get('Event'), dict):
        time_created = event.get('Event', {}).get('System', {}).get('TimeCreated', {})
        timestamp_value = time_created.get('#attributes', {}).get('SystemTime') or time_created.get('@attributes', {}).get('SystemTime')
    
    # Priority 3: Common timestamp field names (including CSV)
    if not timestamp_value:
        timestamp_fields = [
            '@timestamp', 'timestamp', 'Time', 'time', 'datetime',
            'TimeCreated', 'timeCreated', 'event_time', 'eventtime',
            'created_at', 'createdAt', 'date', 'Date',
            'TIME_CREATED', 'CreatedDate', 'created'
        ]
        
        for field in timestamp_fields:
            if field in event and event[field]:
                timestamp_value = event[field]
                break
    
    # Convert to ISO format
    if timestamp_value:
        try:
            ts_str = str(timestamp_value)
            
            # Already ISO format (with T separator)
            if 'T' in ts_str:
                # Normalize timezone
                ts_str = ts_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(ts_str)
                return dt.isoformat()
            
            # Date format (YYYY-MM-DD)
            elif '-' in ts_str and len(ts_str) >= 10:
                dt = datetime.fromisoformat(ts_str)
                return dt.isoformat()
            
            # Unix timestamp (seconds)
            elif ts_str.isdigit():
                ts_int = int(ts_str)
                # Check if milliseconds
                if ts_int > 10000000000:
                    ts_int = ts_int / 1000
                dt = datetime.fromtimestamp(ts_int)
                return dt.isoformat()
            
            # CSV/Firewall formats (MM/DD/YYYY HH:MM:SS or similar)
            else:
                # Try common CSV date formats
                date_formats = [
                    '%m/%d/%Y %H:%M:%S',      # SonicWall: 10/15/2025 12:35:21
                    '%m/%d/%Y %H:%M',          # MM/DD/YYYY HH:MM
                    '%d/%m/%Y %H:%M:%S',      # DD/MM/YYYY HH:MM:SS
                    '%Y/%m/%d %H:%M:%S',      # YYYY/MM/DD HH:MM:SS
                    '%m-%d-%Y %H:%M:%S',      # MM-DD-YYYY HH:MM:SS
                    '%Y-%m-%d %H:%M:%S'       # YYYY-MM-DD HH:MM:SS
                ]
                
                for fmt in date_formats:
                    try:
                        dt = datetime.strptime(ts_str, fmt)
                        return dt.isoformat()
                    except:
                        continue
        
        except Exception as e:
            logger.debug(f"[NORMALIZE] Could not parse timestamp '{timestamp_value}': {e}")
    
    return None


def normalize_event_computer(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract computer/hostname from various event structures
    
    Returns computer name string or None
    """
    computer_name = None
    
    # Priority 1: EVTX structure - System.Computer
    if 'System' in event:
        computer_name = event.get('System', {}).get('Computer')
    
    # Priority 2: EVTX->JSON import - Event.System.Computer
    if not computer_name and 'Event' in event and isinstance(event.get('Event'), dict):
        computer_name = event.get('Event', {}).get('System', {}).get('Computer')
    
    # Priority 3: Common computer field names (including CSV/Firewall)
    if not computer_name:
        computer_fields = [
            'computer_name', 'ComputerName', 'computername',
            'hostname', 'Hostname', 'host_name', 'HostName',
            'machine', 'Machine', 'device', 'Device',
            'agent', 'Agent', 'host', 'Host',
            'Dst. Name',  # SonicWall CSV
            'Source Name', 'Destination Name'
        ]
        
        for field in computer_fields:
            value = event.get(field)
            if value:
                # Handle nested dict (e.g., {"host": {"name": "server1"}})
                if isinstance(value, dict):
                    computer_name = value.get('name') or value.get('hostname')
                elif isinstance(value, str):
                    computer_name = value
                
                if computer_name:
                    break
    
    # Fallback for firewall logs: use device type
    if not computer_name and event.get('source_file_type') == 'CSV':
        # Check if this looks like a firewall log
        if any(field in event for field in ['Src. IP', 'Dst. IP', 'Firewall', 'Category', 'Group']):
            computer_name = 'Firewall'
    
    return computer_name if computer_name else None


def normalize_event_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract event ID from various event structures
    
    Returns event ID string or None
    """
    event_id = None
    
    # Priority 1: EVTX structure - System.EventID
    if 'System' in event and 'EventID' in event.get('System', {}):
        event_id_raw = event['System']['EventID']
        if isinstance(event_id_raw, dict):
            event_id = str(event_id_raw.get('#text', event_id_raw.get('text', '')))
        else:
            event_id = str(event_id_raw)
    
    # Priority 2: EVTX->JSON import - Event.System.EventID
    if not event_id and 'Event' in event and isinstance(event.get('Event'), dict):
        if 'System' in event['Event'] and 'EventID' in event['Event']['System']:
            event_id_raw = event['Event']['System']['EventID']
            if isinstance(event_id_raw, dict):
                event_id = str(event_id_raw.get('#text', event_id_raw.get('text', '')))
            else:
                event_id = str(event_id_raw)
    
    # Priority 3: Common event ID field names (including CSV)
    if not event_id:
        event_id_fields = [
            'event_id', 'eventid', 'EventID', 'event.id',
            'Event',  # SonicWall CSV (event type like "Port Scan Possible")
            'ID',     # SonicWall CSV (numeric ID)
            'event_type', 'EventType', 'event_name', 'EventName'
        ]
        for field in event_id_fields:
            if field in event and event[field]:
                event_id = str(event[field])
                break
    
    # Fallback for CSV: use 'Event' field if it exists
    if not event_id and event.get('source_file_type') == 'CSV':
        if 'Event' in event and event['Event']:
            event_id = 'CSV'  # Generic CSV identifier
    
    return event_id if event_id else None


def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add normalized fields to event for consistent search/display
    
    Adds the following normalized fields:
    - normalized_timestamp: ISO 8601 timestamp
    - normalized_computer: Computer/hostname
    - normalized_event_id: Event ID
    
    Args:
        event: Original event dictionary
    
    Returns:
        Event dictionary with normalized fields added
    """
    # Add normalized timestamp
    normalized_ts = normalize_event_timestamp(event)
    if normalized_ts:
        event['normalized_timestamp'] = normalized_ts
    
    # Add normalized computer name
    normalized_computer = normalize_event_computer(event)
    if normalized_computer:
        event['normalized_computer'] = normalized_computer
    
    # Add normalized event ID
    normalized_id = normalize_event_id(event)
    if normalized_id:
        event['normalized_event_id'] = normalized_id
    
    return event

