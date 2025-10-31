# Main.py Refactoring Plan

## Goal
Break 874-line main.py into modular files for easier maintenance

## New Structure

```
app/
├── main.py (minimal - app setup + blueprint registration)
├── routes/
│   ├── __init__.py
│   ├── auth.py (78 lines) - Login/logout ✓
│   ├── dashboard.py (~150 lines) - Dashboard & stats
│   ├── cases.py (~200 lines) - Case CRUD
│   ├── files.py (~250 lines) - File upload routes
│   └── api.py (~100 lines) - API endpoints (status, etc)
├── models.py (existing)
├── tasks.py (existing)
├── file_processing.py (existing)
└── upload_pipeline.py (existing)
```

## Benefits
1. Easier to find code
2. Smaller files = easier indentation mgmt
3. Easier to fix linting errors
4. Better separation of concerns
5. Can work on one route file without touching others

## Migration Steps
1. ✓ Create routes/ directory
2. ✓ Extract auth routes → auth.py
3. Extract dashboard → dashboard.py
4. Extract case routes → cases.py
5. Extract file upload routes → files.py
6. Extract API routes → api.py
7. Update main.py to minimal bootstrap + blueprint registration
8. Test and verify all routes work
9. Restart services

## Testing Checklist After Refactor
- [ ] Login works
- [ ] Dashboard loads
- [ ] Can create cases
- [ ] Can view cases
- [ ] Can upload files
- [ ] Status API works
- [ ] File processing works
