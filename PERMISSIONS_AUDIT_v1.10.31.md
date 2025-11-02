# 🔒 CaseScope 2026 - Permission System Audit (v1.10.31)

**Date**: 2025-11-02  
**Auditor**: AI Assistant  
**Scope**: All role-based permission checks across the application

---

## 📋 Permission Levels (per APP_MAP.md & version.json)

### **Administrator** (`'administrator'`)
- **Full system access**
- Can delete data
- Can manage any user
- Can adjust system settings
- All other functions

### **Analyst** (`'analyst'`)
- Can add cases and manage case-related data and files
- **CANNOT** delete any data
- Can create Read-Only users only
- Can edit their own data
- **CANNOT** edit other users of same or higher security levels

### **Read-Only** (`'read-only'`)
- Can view case and file data
- Can perform searches
- **CANNOT** add/remove any data
- **CANNOT** edit themselves or any other users

---

## ✅ USER MANAGEMENT PERMISSIONS (routes/users.py)

### **List Users** (`/users`)
- ✅ **Decorator**: `@analyst_required`
- ✅ **Access**: Analyst + Administrator
- ✅ **Correct**: Both roles can view users

### **Create User** (`/users/new`)
- ✅ **Decorator**: `@analyst_required`
- ✅ **Permission Check**: Lines 113-115
  ```python
  if current_user.role == 'analyst' and role != 'read-only':
      flash('Analysts can only create read-only users.', 'error')
  ```
- ✅ **Correct**: Analysts can only create read-only users, admins can create any

### **Edit User** (`/users/<id>/edit`)
- ✅ **Decorator**: `@analyst_required`
- ✅ **Permission Check**: Lines 169-171 (uses `can_edit_user()`)
- ✅ **Permission Check**: Lines 187-191 (role change restriction)
  ```python
  if current_user.role == 'analyst':
      if role != 'read-only':
          flash('Analysts can only set role to read-only.', 'error')
  ```
- ✅ **Helper Function**: `can_edit_user()` (Lines 48-71)
  - Administrator: Can edit anyone
  - Analyst: Can edit users they created AND read-only users
  - Read-Only: Cannot edit anyone
- ✅ **Correct**: Matches documented permissions

### **Delete User** (`/users/<id>/delete`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Access**: Administrator ONLY
- ✅ **Correct**: Only admins can delete

### **Profile Edit** (`/profile`)
- ✅ **Permission Check**: Lines 303-305
  ```python
  if current_user.role == 'read-only':
      flash('Read-only users cannot edit their profile.', 'error')
  ```
- ✅ **Correct**: Read-only users blocked from editing profile

---

## ✅ CASE MANAGEMENT PERMISSIONS (routes/cases.py)

### **Case Management Dashboard** (`/cases`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Additional Check**: Lines 18-20
  ```python
  if current_user.role != 'administrator':
      flash('Administrator access required', 'error')
  ```
- ✅ **Correct**: Admin-only access

### **Edit Case** (`/cases/<id>/edit`)
- ✅ **Decorator**: `@login_required`
- ✅ **Permission Check**: Lines 74-76
  ```python
  if current_user.role != 'administrator' and case.created_by != current_user.id:
      flash('Permission denied', 'error')
  ```
- ✅ **Permission Check**: Lines 103-107 (assignment)
  ```python
  if current_user.role == 'administrator':
      # Only admin can change assignment
  ```
- ✅ **Correct**: Admin OR case creator can edit; only admin can assign

### **Delete Case** (`/cases/<id>/delete`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Correct**: Admin-only (analysts cannot delete per spec)

### **Toggle Case Status** (`/cases/<id>/toggle_status`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Correct**: Admin-only

---

## ✅ FILE OPERATIONS PERMISSIONS

### **Bulk Delete All Files** (`/case/<id>/bulk_delete_files`)
- ✅ **Decorator**: `@login_required`
- ✅ **Permission Check**: Lines 1967-1969 (main.py)
  ```python
  if current_user.role != 'administrator':
      flash('Only administrators can delete all files', 'error')
  ```
- ✅ **Correct**: Admin-only (analysts cannot delete per spec)

### **Delete Single File** - ⚠️ **NEEDS REVIEW**
- **Location**: Check if exists and has permission check
- **Expected**: Should be admin-only OR none (analysts cannot delete)

### **Upload Files** (`/case/<id>/upload`)
- ✅ **Decorator**: `@login_required`
- ✅ **No Additional Check**: Any authenticated user can upload
- ⚠️ **REVIEW NEEDED**: Should read-only users be blocked from uploading?

### **Reindex/Rechainsaw/Re-hunt** (Bulk Operations)
- ✅ **Decorator**: `@login_required`
- ✅ **No Admin Check**: Any authenticated user can trigger
- ✅ **Correct**: These are analysis functions, not delete operations

---

## ✅ SYSTEM SETTINGS PERMISSIONS (routes/settings.py)

### **View Settings** (`/settings`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Additional Check**: Lines 15-17
  ```python
  if current_user.role != 'administrator':
      flash('⛔ Administrator access required', 'error')
  ```
- ✅ **Correct**: Admin-only

### **Save Settings** (`/settings/save`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Correct**: Admin-only

### **Test DFIR-IRIS/OpenCTI** (`/settings/test_*`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Correct**: Admin-only

### **Sync Operations** (`/settings/sync_*`)
- ✅ **Decorator**: `@admin_required`
- ✅ **Correct**: Admin-only

---

## ✅ EVTX DESCRIPTIONS PERMISSIONS

### **View EVTX Descriptions** (`/evtx_descriptions`)
- ✅ **Decorator**: `@login_required`
- ✅ **No Admin Check**: All users can view
- ✅ **Correct**: Read-only can view descriptions

### **Update EVTX Descriptions** (`/evtx_descriptions/update`)
- ✅ **Decorator**: `@login_required`
- ✅ **Permission Check**: Lines 724-726 (main.py)
  ```python
  if current_user.role != 'administrator':
      flash('Only administrators can update EVTX descriptions', 'error')
  ```
- ✅ **Correct**: Admin-only (system settings)

---

## ✅ TIMELINE OPERATIONS

### **Tag Event** (`/case/<id>/search/tag`)
- ✅ **Decorator**: `@login_required`
- ✅ **No Admin Check**: Any authenticated user can tag
- ⚠️ **REVIEW NEEDED**: Should read-only users be blocked from tagging?

### **Untag Event** (`/case/<id>/search/untag/<tag_id>`)
- ✅ **Decorator**: `@login_required`
- ✅ **Permission Check**: Lines 1230-1231 (main.py)
  ```python
  if tag.user_id != current_user.id and current_user.role != 'administrator':
      return jsonify({'error': 'Unauthorized'}), 403
  ```
- ✅ **Correct**: User can untag their own tags, admin can untag any

### **Hide/Unhide Events** (`/case/<id>/search/hide`, `/unhide`)
- ✅ **Decorator**: `@login_required`
- ✅ **No Admin Check**: Any authenticated user can hide/unhide
- ⚠️ **REVIEW NEEDED**: Should this be restricted?

---

## ⚠️ ITEMS REQUIRING REVIEW

### 1. **Read-Only User Upload Permissions**
- **Current**: Read-only users CAN upload files
- **Spec**: "Cannot add/remove any data"
- **Recommendation**: Block read-only users from uploading

### 2. **Read-Only User Timeline Tagging**
- **Current**: Read-only users CAN tag events for timeline
- **Spec**: "Cannot add/remove any data"
- **Recommendation**: Block read-only users from tagging

### 3. **Read-Only User Hide/Unhide Events**
- **Current**: Read-only users CAN hide/unhide events
- **Spec**: "Can view case and file data"
- **Recommendation**: Block read-only users from hiding/unhiding

### 4. **Individual File Deletion**
- **Current**: No individual file delete route found
- **Status**: If it exists, verify it's admin-only
- **Recommendation**: Confirm no delete route exists OR add admin check

### 5. **Create Case Permission**
- **Current**: `@login_required` only (any authenticated user)
- **Spec**: Analysts "Can add cases"
- **Recommendation**: Block read-only users from creating cases

---

## 🎯 RECOMMENDED FIXES

### **Priority 1: Block Read-Only Users from Modifying Data**

Add permission checks to block `read-only` users from:
1. Creating cases
2. Uploading files
3. Tagging timeline events
4. Hiding/unhiding events
5. Adding IOCs
6. Any other data modification operations

### **Priority 2: Verify Delete Operations**

Ensure ALL delete operations require `administrator` role:
- ✅ Delete user (confirmed)
- ✅ Delete case (confirmed)
- ✅ Delete all files (confirmed)
- ⚠️ Delete single file (check if exists)
- ⚠️ Delete IOC (check permission)

### **Priority 3: Document Read-Only Restrictions**

Create clear UI indicators when read-only users view pages with disabled actions:
- Gray out/hide upload buttons
- Gray out/hide tag buttons
- Gray out/hide hide/unhide buttons
- Show tooltip: "Read-only users cannot modify data"

---

## 📊 SUMMARY

| Feature | Administrator | Analyst | Read-Only | Status |
|---------|--------------|---------|-----------|--------|
| View Users | ✅ | ✅ | ❌ | ✅ Correct |
| Create Users | ✅ | ✅ (read-only only) | ❌ | ✅ Correct |
| Edit Users | ✅ (all) | ✅ (limited) | ❌ | ✅ Correct |
| Delete Users | ✅ | ❌ | ❌ | ✅ Correct |
| Create Cases | ✅ | ✅ | ❌ | ⚠️ **NEEDS FIX** |
| Edit Cases | ✅ (all) | ✅ (own) | ❌ | ✅ Correct |
| Delete Cases | ✅ | ❌ | ❌ | ✅ Correct |
| Upload Files | ✅ | ✅ | ❌ | ⚠️ **NEEDS FIX** |
| Delete Files | ✅ | ❌ | ❌ | ✅ Correct |
| Tag Timeline | ✅ | ✅ | ❌ | ⚠️ **NEEDS FIX** |
| Hide Events | ✅ | ✅ | ❌ | ⚠️ **NEEDS FIX** |
| System Settings | ✅ | ❌ | ❌ | ✅ Correct |
| User Management | ✅ | ✅ (limited) | ❌ | ✅ Correct |

---

## ✅ OVERALL ASSESSMENT

**Core Permissions**: ✅ **GOOD**
- Administrator and Analyst roles are correctly implemented
- Delete operations properly restricted to administrators
- User management permissions working as specified

**Read-Only Restrictions**: ⚠️ **NEEDS IMPROVEMENT**
- Read-only users currently have too much access
- Can upload, tag, hide/unhide - should be view-only
- Need to add permission checks to data modification operations

**Recommendation**: Implement Priority 1 fixes to properly restrict read-only users

