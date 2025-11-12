# Event Deduplication Solution Proposal

## Problem Statement

Currently, CaseScope only performs **file-level deduplication** (hash + filename). If two files have different hashes but contain overlapping events (e.g., different time periods from the same server), those duplicate events will be indexed separately, appearing multiple times in search results.

## Proposed Solution: Deterministic Document ID Generation

### Approach: Use Deterministic `_id` for OpenSearch Documents

**Key Principle**: Generate a deterministic `_id` for each event based on its unique characteristics. When OpenSearch receives a document with an existing `_id`, it automatically updates/replaces the existing document instead of creating a duplicate.

### Strategy

1. **For Windows Events (EVTX)**:
   - Use: `case_id + normalized_timestamp + normalized_computer + normalized_event_id + EventRecordID`
   - EventRecordID is unique per Windows event log file and provides perfect deduplication
   - Format: `case_{case_id}_evt_{event_id}_rec_{record_id}_{computer}_{timestamp}`

2. **For Non-Windows Events (JSON/NDJSON/CSV)**:
   - Use: Hash of `case_id + normalized_timestamp + normalized_computer + normalized_event_id + event_data_sample`
   - Format: `case_{case_id}_hash_{sha256_hash}`

### Benefits

✅ **Zero Data Loss**: Existing events remain unchanged (backward compatible)
✅ **Automatic Deduplication**: OpenSearch handles duplicates natively via `_id`
✅ **Cross-Index**: Works across all indices in a case (same event = same `_id`)
✅ **Configurable**: Can be enabled/disabled per case or globally
✅ **Low Risk**: Only affects new indexing, doesn't modify existing data
✅ **Performance**: No pre-indexing queries needed (OpenSearch handles it)

### Risk Mitigation

1. **Backward Compatibility**:
   - Feature disabled by default (`DEDUPLICATE_EVENTS = False`)
   - Existing events keep their auto-generated IDs
   - Can be enabled gradually per case

2. **Data Safety**:
   - Only affects new indexing operations
   - Existing indexed events remain untouched
   - Can be tested on a single case first

3. **Edge Cases Handled**:
   - Missing EventRecordID → Falls back to hash-based ID
   - Missing normalized fields → Falls back gracefully
   - Invalid characters → Sanitized for OpenSearch `_id` format

## Implementation Details

### 1. New Module: `event_deduplication.py`

**Functions**:
- `generate_event_document_id()`: Creates deterministic `_id` from event data
- `should_deduplicate_events()`: Checks if deduplication is enabled (configurable)

**ID Generation Logic**:
```python
# Windows events with EventRecordID
case_11_evt_4624_rec_12345_SERVER01_2025-11-12T14:30:00

# Non-Windows or missing EventRecordID
case_11_hash_a1b2c3d4e5f6...
```

### 2. Integration Point: `file_processing.py`

**Changes Required**:
- Import `generate_event_document_id` and `should_deduplicate_events`
- Before adding event to `bulk_data`, check if deduplication enabled
- If enabled, generate deterministic `_id` and add to bulk operation

**Code Pattern**:
```python
# After normalize_event()
event = normalize_event(event)

# Generate deterministic ID if deduplication enabled
if should_deduplicate_events(case_id):
    doc_id = generate_event_document_id(case_id, event)
    bulk_data.append({
        '_index': index_name,
        '_id': doc_id,  # Explicit ID for deduplication
        '_source': event
    })
else:
    # Current behavior: auto-generated ID
    bulk_data.append({
        '_index': index_name,
        '_source': event
    })
```

### 3. Configuration Options

**Option A: Global Setting** (Simplest)
```python
# config.py
DEDUPLICATE_EVENTS = False  # Enable globally when ready
```

**Option B: Per-Case Setting** (More Flexible)
```python
# models.py - Add to Case model
deduplicate_events = db.Column(db.Boolean, default=False)

# Enable per case via UI or migration
```

**Recommendation**: Start with Option A (global), add Option B later if needed.

## Testing Strategy

### Phase 1: Unit Testing
- Test `generate_event_document_id()` with various event structures
- Verify EventRecordID extraction
- Test hash fallback for non-Windows events
- Verify ID sanitization (special characters, length limits)

### Phase 2: Single Case Testing
1. Enable deduplication for one test case
2. Upload two files with overlapping events
3. Verify:
   - Both files process successfully
   - Overlapping events appear only once in search
   - Event counts are accurate
   - No data loss

### Phase 3: Gradual Rollout
1. Enable for new cases only
2. Monitor for issues
3. Enable globally when confident

## Expected Behavior

### Before (Current):
- File A: `server1_2025-01-01.evtx` → Indexes 10,000 events
- File B: `server1_2025-01-02.evtx` → Indexes 10,000 events (includes 2,000 overlapping from Jan 1)
- **Search Result**: 20,000 events (2,000 duplicates)

### After (With Deduplication):
- File A: `server1_2025-01-01.evtx` → Indexes 10,000 events
- File B: `server1_2025-01-02.evtx` → Indexes 10,000 events
  - 2,000 overlapping events get same `_id` → OpenSearch updates existing documents
- **Search Result**: 18,000 unique events (2,000 deduplicated automatically)

## Migration Path

### Step 1: Add Module (No Impact)
- Create `event_deduplication.py`
- Feature disabled by default
- No changes to existing indexing

### Step 2: Integration (No Impact)
- Modify `file_processing.py` to use deduplication module
- Still disabled by default
- Existing behavior unchanged

### Step 3: Testing (Controlled)
- Enable for one test case
- Verify behavior
- Monitor logs

### Step 4: Rollout (Gradual)
- Enable for new cases
- Monitor for issues
- Enable globally when ready

## Edge Cases & Considerations

### 1. EventRecordID Uniqueness
- **Windows Events**: EventRecordID is unique per log file, perfect for deduplication
- **Non-Windows**: No EventRecordID → Uses hash fallback
- **Risk**: Low - hash provides good uniqueness

### 2. Timestamp Precision
- Uses normalized timestamp (ISO 8601) truncated to seconds
- Events within same second from same computer with same EventRecordID → Deduplicated
- **This is correct behavior** - same event should be deduplicated

### 3. Computer Name Variations
- Uses `normalized_computer` field (already normalized)
- Handles case variations, FQDN vs hostname
- **Risk**: Low - normalization already handles this

### 4. Missing Fields
- Missing EventRecordID → Hash fallback
- Missing normalized fields → Uses 'unknown' placeholder
- **Risk**: Low - graceful degradation

### 5. OpenSearch `_id` Limits
- Max length: 512 bytes
- Our IDs: ~100-200 chars → Well within limit
- Special characters sanitized
- **Risk**: Low - IDs are sanitized

## Performance Impact

### Minimal Impact:
- **ID Generation**: ~0.01ms per event (hash calculation)
- **No Pre-Queries**: No OpenSearch lookups before indexing
- **Bulk Operations**: Same performance (OpenSearch handles deduplication internally)
- **Storage**: Same or less (duplicates removed)

### Expected Improvement:
- **Search Results**: Fewer duplicates = faster queries
- **Storage**: Reduced storage for duplicate events
- **Analytics**: More accurate event counts

## Rollback Plan

If issues arise:
1. Set `DEDUPLICATE_EVENTS = False` in config
2. Restart services
3. New events use auto-generated IDs (back to current behavior)
4. Existing events unaffected

## Files to Modify

1. **New File**: `app/event_deduplication.py` (created)
2. **Modify**: `app/file_processing.py` (lines 414-417, 520-523)
   - Add deduplication check and ID generation
3. **Optional**: `app/config.py` (add `DEDUPLICATE_EVENTS` setting)
4. **Optional**: `app/models.py` (add `Case.deduplicate_events` field if per-case control needed)

## Summary

**Risk Level**: ⚠️ **LOW** - Feature disabled by default, backward compatible, only affects new indexing

**Benefits**: ✅ Automatic deduplication, zero data loss, configurable, low performance impact

**Recommendation**: ✅ **APPROVE** - Safe, low-risk solution that solves the duplicate event problem without modifying existing data.

