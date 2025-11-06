# PostgreSQL Migration: Sequence Fix

**Date**: 2025-11-06
**Issue**: 500 errors after PostgreSQL migration
**Status**: ✅ RESOLVED

## Problem

After migrating from SQLite to PostgreSQL, the application was throwing 500 errors on:
- Login page
- Event search
- Any operation creating new database records

### Error Messages
```
sqlalchemy.exc.PendingRollbackError: This Session's transaction has been rolled back due to a previous exception during flush. 
Original exception was: Instance <AuditLog at 0x75d109511280> has a NULL identity key.
```

```
psycopg2.errors.InsufficientPrivilege: permission denied for sequence audit_log_id_seq
```

## Root Cause

When `pgloader` migrated data from SQLite to PostgreSQL:
1. ✅ Data was copied successfully (430,523 rows)
2. ✅ Tables were created
3. ❌ **Sequences were NOT created** for auto-incrementing primary keys
4. ❌ Columns were not linked to sequences

PostgreSQL requires explicit **sequences** for auto-incrementing IDs. Without them:
- `INSERT` operations fail with NULL identity key
- Application cannot create new records

## Solution

### Step 1: Create Sequences
```sql
CREATE SEQUENCE user_id_seq;
CREATE SEQUENCE case_id_seq;
-- ... (created 16 sequences total)
```

### Step 2: Link Sequences to Columns
```sql
ALTER TABLE "user" ALTER COLUMN id SET DEFAULT nextval('user_id_seq');
ALTER TABLE "case" ALTER COLUMN id SET DEFAULT nextval('case_id_seq');
-- ... (16 tables total)
```

### Step 3: Set Sequence Values
```sql
SELECT setval('user_id_seq', (SELECT MAX(id) FROM "user"));
-- Sets sequence to highest existing ID
-- Next insert will use MAX(id) + 1
```

### Step 4: Grant Permissions
```sql
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO casescope;
ALTER SEQUENCE user_id_seq OWNER TO casescope;
-- ... (16 sequences total)
```

## Sequences Created

| Sequence Name | Set To | Table |
|--------------|--------|-------|
| `user_id_seq` | 1 | user |
| `case_id_seq` | 5 | case |
| `system_settings_id_seq` | 11 | system_settings |
| `sigma_rule_id_seq` | 1 | sigma_rule |
| `case_file_id_seq` | 24,833 | case_file |
| `event_description_id_seq` | 451 | event_description |
| `ioc_id_seq` | 53 | ioc |
| `system_id_seq` | 39 | system |
| `skipped_file_id_seq` | 8,127 | skipped_file |
| `timeline_tag_id_seq` | 676 | timeline_tag |
| `search_history_id_seq` | 1,542 | search_history |
| `ai_report_id_seq` | 29 | ai_report |
| `ai_report_chat_id_seq` | 1 | ai_report_chat |
| `ioc_match_id_seq` | 86,812 | ioc_match |
| `sigma_violation_id_seq` | 317,098 | sigma_violation |
| `audit_log_id_seq` | 30 | audit_log |

## Verification

✅ **Test 1**: Create audit log entry
```python
test_log = AuditLog(user_id=1, action='test_action', details='Testing')
db.session.add(test_log)
db.session.commit()
# Result: ID 31 (30 + 1) ✅
```

✅ **Test 2**: Application restart - no errors
✅ **Test 3**: Login page - working
✅ **Test 4**: Event search - working

## Lesson Learned

**When migrating to PostgreSQL**:
1. Always check sequences exist
2. Verify sequences are linked to columns
3. Set sequences to MAX(id) + 1
4. Grant proper permissions

**For future migrations**: Use SQLAlchemy's `db.create_all()` BEFORE importing data, then sequences will be created automatically.

## Prevention

To check if sequences are missing:
```sql
-- List all sequences
SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public';

-- Verify sequence is linked to column
\d table_name
-- Look for "DEFAULT nextval('sequence_name'::regclass)"
```

If empty, sequences are missing and need to be created manually.

