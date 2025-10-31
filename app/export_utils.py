"""
CSV Export Utilities
Handles CSV generation for event exports
"""

import csv
import io
import json
from datetime import datetime
from typing import List, Dict, Any


def generate_events_csv(events: List[Dict[str, Any]]) -> str:
    """
    Generate CSV from event list
    
    Columns: Date/Time, Description, Computer Name, File Name, Raw Data (JSON)
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Date/Time', 'Description', 'Computer Name', 'File Name', 'Raw Data'])
    
    # Write data rows
    for event in events:
        # Extract fields
        timestamp = event.get('timestamp', '')
        description = event.get('description', '')
        computer_name = event.get('computer_name', '')
        source_file = event.get('source_file', '')
        
        # Convert entire event to JSON for raw data column
        raw_data = json.dumps(event, default=str)
        
        writer.writerow([
            timestamp,
            description,
            computer_name,
            source_file,
            raw_data
        ])
    
    return output.getvalue()

