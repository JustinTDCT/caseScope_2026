# CaseScope Refactoring Proposal
## Code Reduction & Reusability Analysis

**Date**: 2025-11-13  
**Purpose**: Identify opportunities to reduce code length and create reusable components

---

## 📊 Current State Analysis

### Largest Files (Lines of Code)
1. **main.py**: 3,860 lines ⚠️ **CRITICAL**
2. **tasks.py**: 1,658 lines
3. **file_processing.py**: 1,394 lines
4. **routes/files.py**: 1,257 lines
5. **login_analysis.py**: 1,013 lines
6. **search_events.html**: 3,047 lines ⚠️ **CRITICAL**
7. **view_case_enhanced.html**: 1,677 lines

### Code Duplication Patterns Found
- **Case validation**: 29+ occurrences across routes
- **Permission checks**: 23+ occurrences
- **CSV export patterns**: 3+ implementations
- **Bulk operation patterns**: Repeated across IOC/Systems/Known Users
- **Table structures**: Similar HTML across 18+ templates
- **JavaScript bulk functions**: Duplicated patterns

---

## 🎯 Refactoring Opportunities

### **Priority 1: Route-Level Refactoring**

#### **1.1 Case Validation Decorator** ⚠️ **HIGH IMPACT**

**Current**: 29+ routes repeat this pattern:
```python
case = db.session.get(Case, case_id)
if not case:
    flash('Case not found', 'error')
    return redirect(url_for('dashboard'))
```

**Proposed**: Create decorator `@require_case`
```python
# utils/decorators.py
def require_case(f):
    @wraps(f)
    def decorated_function(case_id, *args, **kwargs):
        case = db.session.get(Case, case_id)
        if not case:
            flash('Case not found', 'error')
            return redirect(url_for('dashboard'))
        return f(case_id, case=case, *args, **kwargs)
    return decorated_function

# Usage:
@ioc_bp.route('/case/<int:case_id>/ioc')
@login_required
@require_case
def ioc_management(case_id, case):  # case injected automatically
    # No validation needed!
```

**Impact**: 
- **Reduces**: ~145 lines (29 routes × 5 lines each)
- **Files affected**: All route files
- **Risk**: Low (backward compatible)

---

#### **1.2 Permission Check Decorators** ⚠️ **HIGH IMPACT**

**Current**: 23+ routes repeat permission checks:
```python
if current_user.role == 'read-only':
    return jsonify({'success': False, 'error': 'Read-only users cannot...'}), 403
```

**Proposed**: Create decorators `@require_write_access`, `@require_admin`
```python
# utils/decorators.py
def require_write_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'read-only':
            return jsonify({'success': False, 'error': 'Read-only users cannot perform this action'}), 403
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'administrator':
            return jsonify({'success': False, 'error': 'Administrator access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Usage:
@ioc_bp.route('/case/<int:case_id>/ioc/add', methods=['POST'])
@login_required
@require_case
@require_write_access
def add_ioc(case_id, case):
    # Permission already checked!
```

**Impact**:
- **Reduces**: ~115 lines (23 routes × 5 lines each)
- **Files affected**: routes/ioc.py, routes/systems.py, routes/known_users.py
- **Risk**: Low

---

#### **1.3 CSV Export Utility** ⚠️ **MEDIUM IMPACT**

**Current**: 3+ CSV export implementations (IOC, Systems, Known Users) with similar code:
```python
output = io.StringIO()
writer = csv.writer(output)
writer.writerow(['Column1', 'Column2', ...])
for item in items:
    writer.writerow([...])
output.seek(0)
return Response(output.getvalue(), mimetype='text/csv', ...)
```

**Proposed**: Create `export_csv_response()` utility
```python
# utils/export.py
def export_csv_response(rows, headers, filename_prefix, case_id=None):
    """
    Generate CSV export response
    
    Args:
        rows: List of lists (data rows)
        headers: List of column headers
        filename_prefix: Prefix for filename (e.g., 'iocs', 'systems')
        case_id: Optional case ID for filename
    
    Returns:
        Flask Response with CSV
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    
    filename = f"{filename_prefix}"
    if case_id:
        filename += f"_case_{case_id}"
    filename += f"_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# Usage:
@ioc_bp.route('/case/<int:case_id>/ioc/export_csv')
@login_required
@require_case
def export_iocs_csv(case_id, case):
    iocs = IOC.query.filter_by(case_id=case_id).all()
    rows = [[ioc.ioc_type, ioc.ioc_value, ioc.description or ''] for ioc in iocs]
    return export_csv_response(rows, ['Type', 'Value', 'Description'], 'iocs', case_id)
```

**Impact**:
- **Reduces**: ~60 lines (3 exports × ~20 lines each)
- **Files affected**: routes/ioc.py, routes/systems.py, routes/known_users.py
- **Risk**: Low

---

#### **1.4 Bulk Operation Handler** ⚠️ **HIGH IMPACT**

**Current**: Similar bulk operation patterns across IOC/Systems/Known Users:
- Bulk toggle (enable/disable)
- Bulk delete
- Bulk enrich/sync

**Proposed**: Create generic bulk operation handler
```python
# utils/bulk_operations.py
def handle_bulk_toggle(model_class, case_id, ids, field_name='is_active', value=True):
    """
    Generic bulk toggle handler
    
    Args:
        model_class: SQLAlchemy model class
        case_id: Case ID for filtering
        ids: List of IDs to toggle
        field_name: Field to toggle (default: 'is_active')
        value: Value to set (default: True)
    
    Returns:
        dict: {'success': True, 'processed': N}
    """
    from main import db
    
    items = model_class.query.filter(
        model_class.id.in_(ids),
        model_class.case_id == case_id
    ).all()
    
    for item in items:
        setattr(item, field_name, value)
    
    db.session.commit()
    return {'success': True, 'processed': len(items)}

def handle_bulk_delete(model_class, case_id, ids):
    """Generic bulk delete handler"""
    from main import db
    
    count = model_class.query.filter(
        model_class.id.in_(ids),
        model_class.case_id == case_id
    ).delete(synchronize_session=False)
    
    db.session.commit()
    return {'success': True, 'deleted': count}

# Usage:
@ioc_bp.route('/case/<int:case_id>/ioc/bulk_toggle', methods=['POST'])
@login_required
@require_case
@require_write_access
def bulk_toggle_iocs(case_id, case):
    data = request.get_json()
    return handle_bulk_toggle(IOC, case_id, data['ioc_ids'], 
                             field_name='is_active', 
                             value=(data['action'] == 'enable'))
```

**Impact**:
- **Reduces**: ~200 lines (3 modules × ~65 lines each)
- **Files affected**: routes/ioc.py, routes/systems.py, routes/known_users.py
- **Risk**: Medium (needs careful testing)

---

### **Priority 2: Template Refactoring**

#### **2.1 Reusable Table Component** ⚠️ **HIGH IMPACT**

**Current**: Similar table structures across 18+ templates:
- IOC Management table
- Systems Management table
- Known Users table
- Files tables (multiple)

**Proposed**: Create Jinja2 macro for data tables
```jinja
{# templates/components/data_table.html #}
{% macro data_table(headers, rows, actions=None, bulk_actions=None, sortable=True) %}
<table class="data-table">
    <thead>
        <tr>
            {% if bulk_actions %}
            <th><input type="checkbox" id="selectAll" onclick="toggleSelectAll()"></th>
            {% endif %}
            {% for header in headers %}
            <th>
                {% if sortable %}
                <a href="javascript:void(0)" onclick="sortBy('{{ header.field }}')">
                    {{ header.label }}
                    {% if sort_field == header.field %}
                    <span>{{ '▼' if sort_order == 'desc' else '▲' }}</span>
                    {% endif %}
                </a>
                {% else %}
                {{ header.label }}
                {% endif %}
            </th>
            {% endfor %}
            {% if actions %}
            <th>Actions</th>
            {% endif %}
        </tr>
    </thead>
    <tbody>
        {% for row in rows %}
        <tr>
            {% if bulk_actions %}
            <td><input type="checkbox" class="item-checkbox" value="{{ row.id }}"></td>
            {% endif %}
            {% for cell in row.cells %}
            <td>{{ cell }}</td>
            {% endfor %}
            {% if actions %}
            <td>
                {% for action in actions %}
                <button onclick="{{ action.onclick }}({{ row.id }})">{{ action.label }}</button>
                {% endfor %}
            </td>
            {% endif %}
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endmacro %}
```

**Impact**:
- **Reduces**: ~500+ lines across templates
- **Files affected**: All table templates
- **Risk**: Medium (requires template refactoring)

---

#### **2.2 Reusable Modal Component** ⚠️ **MEDIUM IMPACT**

**Current**: Similar modal patterns for Add/Edit across templates:
- Add IOC modal
- Edit IOC modal
- Add System modal
- Add Known User modal

**Proposed**: Create generic modal macro
```jinja
{# templates/components/modal.html #}
{% macro modal(id, title, form_fields, submit_action, submit_label='Save') %}
<div id="{{ id }}" class="modal" style="display: none;">
    <div class="modal-content">
        <span class="close" onclick="closeModal('{{ id }}')">&times;</span>
        <h2>{{ title }}</h2>
        <form id="{{ id }}Form" onsubmit="{{ submit_action }}(event)">
            {% for field in form_fields %}
            <div class="form-group">
                <label>{{ field.label }}</label>
                {% if field.type == 'select' %}
                <select name="{{ field.name }}" required="{{ field.required }}">
                    {% for option in field.options %}
                    <option value="{{ option.value }}">{{ option.label }}</option>
                    {% endfor %}
                </select>
                {% else %}
                <input type="{{ field.type }}" name="{{ field.name }}" 
                       required="{{ field.required }}" 
                       placeholder="{{ field.placeholder }}">
                {% endif %}
            </div>
            {% endfor %}
            <button type="submit">{{ submit_label }}</button>
        </form>
    </div>
</div>
{% endmacro %}
```

**Impact**:
- **Reduces**: ~300+ lines across templates
- **Files affected**: IOC, Systems, Known Users templates
- **Risk**: Low-Medium

---

#### **2.3 Reusable Bulk Actions Toolbar** ⚠️ **MEDIUM IMPACT**

**Current**: Similar bulk action toolbars across IOC/Systems/Known Users:
```html
<div class="bulk-actions-toolbar">
    <span>Bulk Actions:</span>
    <button onclick="bulkAction1()">Action 1 (<span id="count1">0</span>)</button>
    <button onclick="bulkAction2()">Action 2 (<span id="count2">0</span>)</button>
</div>
```

**Proposed**: Create reusable component
```jinja
{# templates/components/bulk_actions.html #}
{% macro bulk_actions_toolbar(actions, checkbox_class) %}
<div class="bulk-actions-toolbar">
    <span>Bulk Actions:</span>
    {% for action in actions %}
    <button id="{{ action.id }}" 
            onclick="{{ action.function }}()" 
            class="{{ action.class }}" 
            disabled>
        {{ action.label }} (<span id="{{ action.count_id }}">0</span>)
    </button>
    {% endfor %}
</div>
<script>
function updateBulkButtons() {
    const checked = document.querySelectorAll('.{{ checkbox_class }}:checked');
    // Update all button counts and enabled states
}
</script>
{% endmacro %}
```

**Impact**:
- **Reduces**: ~150+ lines across templates
- **Files affected**: IOC, Systems, Known Users templates
- **Risk**: Low

---

### **Priority 3: JavaScript Refactoring**

#### **3.1 Reusable Bulk Operation JavaScript** ⚠️ **HIGH IMPACT**

**Current**: Similar JavaScript functions across templates:
- `toggleSelectAllIOCs()`, `toggleSelectAllSystems()`, `toggleSelectAllUsers()`
- `updateBulkButtons()` (repeated)
- `bulkAction()` functions (similar patterns)

**Proposed**: Create reusable JavaScript module
```javascript
// static/js/bulk_operations.js
class BulkOperations {
    constructor(checkboxClass, bulkActions) {
        this.checkboxClass = checkboxClass;
        this.bulkActions = bulkActions;
        this.init();
    }
    
    init() {
        // Add event listeners to all checkboxes
        document.querySelectorAll(`.${this.checkboxClass}`).forEach(cb => {
            cb.addEventListener('change', () => this.updateButtons());
        });
    }
    
    toggleSelectAll() {
        const selectAll = document.getElementById('selectAll');
        const checkboxes = document.querySelectorAll(`.${this.checkboxClass}`);
        checkboxes.forEach(cb => cb.checked = selectAll.checked);
        this.updateButtons();
    }
    
    updateButtons() {
        const checked = document.querySelectorAll(`.${this.checkboxClass}:checked`);
        const count = checked.length;
        
        this.bulkActions.forEach(action => {
            const btn = document.getElementById(action.buttonId);
            const countSpan = document.getElementById(action.countId);
            btn.disabled = count === 0;
            countSpan.textContent = count;
        });
    }
    
    getSelectedIds() {
        const checked = document.querySelectorAll(`.${this.checkboxClass}:checked`);
        return Array.from(checked).map(cb => cb.value);
    }
    
    async performBulkAction(actionUrl, actionData) {
        const ids = this.getSelectedIds();
        if (ids.length === 0) return;
        
        const response = await fetch(actionUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...actionData, ids})
        });
        
        return response.json();
    }
}

// Usage in template:
<script>
const iocBulkOps = new BulkOperations('ioc-checkbox', [
    {buttonId: 'bulkEnableBtn', countId: 'countEnable'},
    {buttonId: 'bulkDisableBtn', countId: 'countDisable'}
]);

function bulkEnableIOCs() {
    iocBulkOps.performBulkAction('/case/{{ case.id }}/ioc/bulk_toggle', {action: 'enable'});
}
</script>
```

**Impact**:
- **Reduces**: ~400+ lines across templates
- **Files affected**: IOC, Systems, Known Users templates
- **Risk**: Medium (requires JavaScript refactoring)

---

### **Priority 4: Database Query Refactoring**

#### **4.1 Query Builder Utility** ⚠️ **MEDIUM IMPACT**

**Current**: Repeated query patterns:
```python
# Pagination
page = request.args.get('page', 1, type=int)
per_page = request.args.get('per_page', 50, type=int)
pagination = query.paginate(page=page, per_page=per_page, error_out=False)

# Sorting
if sort_field == 'field1':
    if sort_order == 'asc':
        query = query.order_by(Model.field1.asc())
    else:
        query = query.order_by(Model.field1.desc())
```

**Proposed**: Create query builder utility
```python
# utils/query_builder.py
def build_paginated_query(model_class, case_id, filters=None, sort_field='created_at', 
                         sort_order='desc', per_page=50):
    """
    Build paginated and sorted query
    
    Args:
        model_class: SQLAlchemy model class
        case_id: Case ID for filtering
        filters: Dict of filters (e.g., {'hidden': False})
        sort_field: Field to sort by
        sort_order: 'asc' or 'desc'
        per_page: Items per page
    
    Returns:
        Pagination object
    """
    from flask import request
    
    query = model_class.query.filter_by(case_id=case_id)
    
    # Apply filters
    if filters:
        for field, value in filters.items():
            query = query.filter(getattr(model_class, field) == value)
    
    # Apply sorting
    sort_attr = getattr(model_class, sort_field, None)
    if sort_attr:
        if sort_order == 'asc':
            query = query.order_by(sort_attr.asc())
        else:
            query = query.order_by(sort_attr.desc())
    
    # Paginate
    page = request.args.get('page', 1, type=int)
    return query.paginate(page=page, per_page=per_page, error_out=False)

# Usage:
@systems_bp.route('/case/<int:case_id>/systems')
@login_required
@require_case
def systems_management(case_id, case):
    pagination = build_paginated_query(
        System, case_id,
        filters={'hidden': False} if current_user.role != 'administrator' else None,
        sort_field=request.args.get('sort', 'system_name'),
        sort_order=request.args.get('order', 'asc')
    )
    systems = pagination.items
    # ...
```

**Impact**:
- **Reduces**: ~150+ lines across routes
- **Files affected**: routes/systems.py, routes/known_users.py, routes/files.py
- **Risk**: Low-Medium

---

#### **4.2 Stats Calculation Utility** ⚠️ **LOW-MEDIUM IMPACT**

**Current**: Similar stats calculation patterns:
```python
stats = {
    'servers': System.query.filter_by(case_id=case_id, system_type='server', hidden=False).count(),
    'workstations': System.query.filter_by(case_id=case_id, system_type='workstation', hidden=False).count(),
    # ... repeated for each type
}
```

**Proposed**: Create generic stats calculator
```python
# utils/stats.py
def calculate_type_stats(model_class, case_id, type_field='system_type', 
                        type_values=None, filters=None):
    """
    Calculate statistics by type
    
    Args:
        model_class: SQLAlchemy model class
        case_id: Case ID
        type_field: Field name for type (e.g., 'system_type', 'ioc_type')
        type_values: List of type values to count (if None, counts all unique values)
        filters: Additional filters dict
    
    Returns:
        dict: {type_value: count, ...}
    """
    base_query = model_class.query.filter_by(case_id=case_id)
    
    if filters:
        for field, value in filters.items():
            base_query = base_query.filter(getattr(model_class, field) == value)
    
    if type_values:
        stats = {}
        for type_val in type_values:
            stats[type_val] = base_query.filter(
                getattr(model_class, type_field) == type_val
            ).count()
    else:
        # Count all unique types
        from sqlalchemy import func
        results = base_query.with_entities(
            getattr(model_class, type_field),
            func.count(model_class.id)
        ).group_by(getattr(model_class, type_field)).all()
        stats = {type_val: count for type_val, count in results}
    
    return stats

# Usage:
stats = calculate_type_stats(
    System, case_id, 
    type_field='system_type',
    type_values=['server', 'workstation', 'firewall', 'switch', 'printer', 'actor_system'],
    filters={'hidden': False} if current_user.role != 'administrator' else None
)
```

**Impact**:
- **Reduces**: ~100+ lines across routes
- **Files affected**: routes/systems.py, routes/ioc.py
- **Risk**: Low

---

### **Priority 5: Main.py Refactoring**

#### **5.1 Break Down main.py** ⚠️ **CRITICAL**

**Current**: `main.py` is 3,860 lines (too large!)

**Proposed**: Split into modules:
```
main.py (200 lines) - Flask app initialization only
├── routes/
│   ├── dashboard.py - Dashboard routes
│   ├── search.py - Search/event routes
│   ├── upload.py - Upload routes (move from upload_integration.py)
│   └── ... (other routes already separated)
├── utils/
│   ├── decorators.py - Route decorators
│   ├── query_builder.py - Query utilities
│   ├── export.py - CSV export utilities
│   └── bulk_operations.py - Bulk operation handlers
└── templates/
    └── components/ - Reusable template components
```

**Impact**:
- **Reduces**: main.py from 3,860 → ~200 lines
- **Improves**: Maintainability, testability
- **Risk**: High (major refactoring)

---

### **Priority 6: Template Refactoring**

#### **6.1 Break Down search_events.html** ⚠️ **CRITICAL**

**Current**: `search_events.html` is 3,047 lines (too large!)

**Proposed**: Split into components:
```
search_events.html (200 lines) - Main template
├── components/
│   ├── search_form.html - Search form component
│   ├── search_results.html - Results table component
│   ├── event_modal.html - Event details modal
│   ├── login_analysis_modals.html - Login analysis modals
│   └── filters_panel.html - Filter sidebar
└── static/js/
    └── search_events.js - All JavaScript (extract from template)
```

**Impact**:
- **Reduces**: search_events.html from 3,047 → ~200 lines
- **Improves**: Maintainability, reusability
- **Risk**: Medium-High

---

## 📋 Refactoring Priority Matrix

| Priority | Refactoring | Impact | Risk | Estimated Reduction |
|----------|------------|--------|------|-------------------|
| **P1** | Case Validation Decorator | High | Low | ~145 lines |
| **P1** | Permission Check Decorators | High | Low | ~115 lines |
| **P1** | Bulk Operation Handler | High | Medium | ~200 lines |
| **P1** | Reusable Table Component | High | Medium | ~500 lines |
| **P2** | CSV Export Utility | Medium | Low | ~60 lines |
| **P2** | Query Builder Utility | Medium | Low-Medium | ~150 lines |
| **P2** | Reusable Modal Component | Medium | Low-Medium | ~300 lines |
| **P2** | Bulk Actions Toolbar | Medium | Low | ~150 lines |
| **P3** | JavaScript Bulk Operations | High | Medium | ~400 lines |
| **P3** | Stats Calculation Utility | Low-Medium | Low | ~100 lines |
| **P4** | Break Down main.py | Critical | High | ~3,660 lines |
| **P4** | Break Down search_events.html | Critical | Medium-High | ~2,847 lines |

**Total Estimated Reduction**: ~8,627 lines of code

---

## 🎯 Implementation Strategy

### **Phase 1: Low-Risk Utilities (Week 1)**
1. ✅ Create `utils/decorators.py` - Case validation & permission decorators
2. ✅ Create `utils/export.py` - CSV export utility
3. ✅ Create `utils/query_builder.py` - Query builder utility
4. ✅ Create `utils/stats.py` - Stats calculation utility
5. ✅ Refactor routes to use new utilities

**Expected Reduction**: ~470 lines

---

### **Phase 2: Template Components (Week 2)**
1. ✅ Create `templates/components/data_table.html` macro
2. ✅ Create `templates/components/modal.html` macro
3. ✅ Create `templates/components/bulk_actions.html` macro
4. ✅ Refactor IOC/Systems/Known Users templates

**Expected Reduction**: ~950 lines

---

### **Phase 3: JavaScript Refactoring (Week 3)**
1. ✅ Create `static/js/bulk_operations.js` class
2. ✅ Extract JavaScript from templates to separate files
3. ✅ Create reusable JavaScript utilities

**Expected Reduction**: ~400 lines

---

### **Phase 4: Major Refactoring (Week 4)**
1. ✅ Break down `main.py` into modules
2. ✅ Break down `search_events.html` into components
3. ✅ Extract JavaScript from templates

**Expected Reduction**: ~6,500 lines

---

## 📊 Expected Results

### **Before Refactoring**
- **Total Python**: ~24,080 lines
- **Total Templates**: ~14,567 lines
- **Largest File**: main.py (3,860 lines)
- **Code Duplication**: High

### **After Refactoring**
- **Total Python**: ~15,453 lines (**-36% reduction**)
- **Total Templates**: ~11,120 lines (**-24% reduction**)
- **Largest File**: ~1,400 lines (file_processing.py)
- **Code Duplication**: Low

### **Benefits**
✅ **Maintainability**: Easier to find and fix bugs  
✅ **Testability**: Smaller, focused functions easier to test  
✅ **Reusability**: Common patterns extracted to utilities  
✅ **Readability**: Cleaner, more focused code  
✅ **Consistency**: Standardized patterns across codebase  
✅ **Performance**: No performance impact (same functionality)

---

## ⚠️ Risks & Mitigation

### **Risk 1: Breaking Changes**
- **Mitigation**: Implement incrementally, test each phase
- **Rollback**: Git branches for each phase

### **Risk 2: Template Refactoring Complexity**
- **Mitigation**: Start with simple macros, test thoroughly
- **Fallback**: Keep old templates as backup

### **Risk 3: JavaScript Refactoring**
- **Mitigation**: Extract to separate files first, then refactor
- **Testing**: Test all bulk operations after refactoring

---

## 📝 Recommendations

### **Immediate Actions (This Week)**
1. ✅ Create `utils/decorators.py` with `@require_case` and permission decorators
2. ✅ Refactor 5-10 routes to use new decorators
3. ✅ Create `utils/export.py` for CSV exports
4. ✅ Refactor IOC/Systems CSV exports to use utility

### **Short Term (Next 2 Weeks)**
1. ✅ Create template component macros
2. ✅ Refactor IOC/Systems/Known Users templates
3. ✅ Create JavaScript bulk operations class
4. ✅ Extract JavaScript from templates

### **Long Term (Next Month)**
1. ✅ Break down `main.py` into modules
2. ✅ Break down `search_events.html` into components
3. ✅ Create comprehensive test suite
4. ✅ Document all reusable components

---

## 🔍 Code Quality Metrics

### **Current Metrics**
- **Cyclomatic Complexity**: High (large functions)
- **Code Duplication**: ~15-20%
- **File Size**: Several files >1,000 lines
- **Function Length**: Some functions >200 lines

### **Target Metrics**
- **Cyclomatic Complexity**: Low-Medium (<10 per function)
- **Code Duplication**: <5%
- **File Size**: <500 lines per file
- **Function Length**: <50 lines per function

---

## ✅ Conclusion

This refactoring proposal identifies **8,627+ lines of code reduction** opportunities through:
1. **Route-level utilities** (decorators, query builders)
2. **Template components** (reusable macros)
3. **JavaScript modules** (reusable classes)
4. **File decomposition** (breaking down large files)

**Priority**: Start with low-risk utilities (Phase 1), then move to templates and JavaScript, finally tackle major file decomposition.

**Timeline**: 4 weeks for complete refactoring
**Risk Level**: Low-Medium (incremental approach)
**Expected Benefit**: 30-40% code reduction, significantly improved maintainability

