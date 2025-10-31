#!/usr/bin/env python3
"""
Backfill source_file_type field for existing events in OpenSearch

This script scans all events and adds the source_file_type field based on 
the event's structure (EVTX, EDR, JSON, CSV detection logic).
"""

from main import app, opensearch_client
from opensearchpy import helpers as opensearch_helpers
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def infer_source_file_type(event_source):
    """
    Infer source file type from event structure
    Same logic as file_processing.py
    """
    # Check for EVTX structure
    if 'System' in event_source:
        return 'EVTX'
    if 'Event' in event_source and isinstance(event_source.get('Event'), dict):
        if 'System' in event_source['Event']:
            return 'EVTX'
    
    # Check for EDR structure
    if '@timestamp' in event_source:
        if 'process' in event_source or 'host' in event_source or 'agent' in event_source:
            return 'EDR'
    
    if 'event' in event_source and isinstance(event_source.get('event'), dict):
        event_dict = event_source['event']
        if 'kind' in event_dict or 'category' in event_dict:
            return 'EDR'
    
    if 'ecs' in event_source:
        return 'EDR'
    
    # Check for CSV structure (would have row_number field)
    if 'row_number' in event_source:
        return 'CSV'
    
    # Default to JSON
    return 'JSON'


def backfill_source_file_type(index_pattern='case_*', batch_size=1000):
    """
    Backfill source_file_type for all events in matching indices
    """
    logger.info(f"Starting backfill for index pattern: {index_pattern}")
    
    # Use scroll API to iterate through all events
    query = {
        'query': {
            'bool': {
                'must_not': {
                    'exists': {'field': 'source_file_type'}
                }
            }
        }
    }
    
    total_updated = 0
    batch = []
    
    try:
        # Scroll through all documents
        for doc in opensearch_helpers.scan(
            opensearch_client,
            index=index_pattern,
            query=query,
            scroll='5m',
            size=batch_size
        ):
            # Infer type
            source_type = infer_source_file_type(doc['_source'])
            
            # Prepare update action
            batch.append({
                '_op_type': 'update',
                '_index': doc['_index'],
                '_id': doc['_id'],
                'doc': {'source_file_type': source_type}
            })
            
            # Bulk update when batch is full
            if len(batch) >= batch_size:
                success, errors = opensearch_helpers.bulk(
                    opensearch_client,
                    batch,
                    raise_on_error=False
                )
                total_updated += success
                if errors:
                    logger.warning(f"Batch had {len(errors)} errors")
                
                logger.info(f"Progress: {total_updated:,} events updated")
                batch = []
        
        # Update remaining batch
        if batch:
            success, errors = opensearch_helpers.bulk(
                opensearch_client,
                batch,
                raise_on_error=False
            )
            total_updated += success
            if errors:
                logger.warning(f"Final batch had {len(errors)} errors")
        
        logger.info(f"✓ Backfill complete: {total_updated:,} events updated")
        return total_updated
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        raise


if __name__ == '__main__':
    with app.app_context():
        backfill_source_file_type()

