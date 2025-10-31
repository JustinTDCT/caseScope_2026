#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Utility Functions
"""

import re
import hashlib


def sanitize_filename(filename):
    """
    Sanitize filename for safe filesystem and OpenSearch index usage
    
    Rules:
    - Convert to lowercase
    - Replace spaces with underscores
    - Remove special characters (keep alphanumeric, underscore, hyphen, dot)
    - Strip leading/trailing dots and underscores
    """
    # Convert to lowercase
    name = filename.lower()
    
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    
    # Remove special characters
    name = re.sub(r'[^a-z0-9_\-.]', '', name)
    
    # Remove multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    
    # Strip leading/trailing dots and underscores
    name = name.strip('._')
    
    return name


def make_index_name(case_id, filename):
    """
    Create OpenSearch index name from case ID and filename
    
    Format: case_{case_id}_{sanitized_filename}
    Example: case_1_desktop-pc_security.evtx
    """
    sanitized = sanitize_filename(filename)
    
    # Remove file extension for index name
    if '.' in sanitized:
        sanitized = sanitized.rsplit('.', 1)[0]
    
    return f"case_{case_id}_{sanitized}"


def hash_file(file_path, algorithm='sha256'):
    """
    Calculate file hash
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (default: sha256)
    
    Returns:
        str: Hex digest of file hash
    """
    hasher = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    
    return hasher.hexdigest()

