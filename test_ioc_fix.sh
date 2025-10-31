#!/bin/bash

# IOC Fix Verification Script
# Tests the new query_string method vs the old simple_query_string method

echo "================================================================================"
echo "IOC HUNTING FIX VERIFICATION - v1.10.7"
echo "================================================================================"
echo ""
echo "Testing: Case 2 IOCs with nested field search"
echo ""

# Test 1: IP in CSV (flat structure - should work with both methods)
echo "### TEST 1: IP Address in CSV (Flat Structure) ###"
echo "IOC: 46.62.206.119"
echo "Index: case_2_log_18c2417291f0_2025-10-30_14-29-47"
echo ""

curl -s -X POST "http://localhost:9200/case_2_log_18c2417291f0_2025-10-30_14-29-47/_search" \
  -H 'Content-Type: application/json' \
  -d'{
  "query": {
    "query_string": {
      "query": "*46.62.206.119*",
      "analyze_wildcard": true,
      "lenient": true
    }
  },
  "size": 0
}' | jq -r '"  ✅ NEW METHOD (query_string):        \(.hits.total.value) hits"'

curl -s -X POST "http://localhost:9200/case_2_log_18c2417291f0_2025-10-30_14-29-47/_search" \
  -H 'Content-Type: application/json' \
  -d'{
  "query": {
    "simple_query_string": {
      "query": "46.62.206.119",
      "fields": ["*"]
    }
  },
  "size": 0
}' | jq -r '"  ❌ OLD METHOD (simple_query_string): \(.hits.total.value) hits"'

echo ""
echo "---"
echo ""

# Test 2: Check if the fix is active in the code
echo "### TEST 2: Code Verification ###"
echo "Checking if file_processing.py contains the fix..."
echo ""

if grep -q "query_string" /opt/casescope/app/file_processing.py && \
   grep -q "Using query_string for wildcard search" /opt/casescope/app/file_processing.py; then
    echo "  ✅ Code contains the new query_string logic"
else
    echo "  ❌ Code does NOT contain the fix"
fi

if grep -q "\"version\": \"1.10.7\"" /opt/casescope/app/version.json; then
    echo "  ✅ Version updated to 1.10.7"
else
    echo "  ❌ Version NOT updated"
fi

echo ""
echo "---"
echo ""

# Test 3: Service Status
echo "### TEST 3: Service Status ###"
echo ""

if systemctl is-active --quiet casescope; then
    echo "  ✅ casescope service is running"
else
    echo "  ❌ casescope service is NOT running"
fi

if systemctl is-active --quiet casescope-worker; then
    echo "  ✅ casescope-worker service is running"
else
    echo "  ❌ casescope-worker service is NOT running"
fi

echo ""
echo "---"
echo ""

# Test 4: Database IOC Check
echo "### TEST 4: Active IOCs for Case 2 ###"
echo ""

/opt/casescope/venv/bin/python3 << 'PYEOF'
from sqlalchemy import create_engine, text
engine = create_engine('sqlite:////opt/casescope/data/casescope.db')
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT ioc_type, ioc_value 
        FROM ioc 
        WHERE case_id = 2 AND is_active = 1
        ORDER BY ioc_type, ioc_value
    """))
    rows = result.fetchall()
    print(f"  Total Active IOCs: {len(rows)}")
    for ioc_type, ioc_value in rows:
        print(f"    - {ioc_type:15s} : {ioc_value}")
PYEOF

echo ""
echo "================================================================================"
echo "NEXT STEPS:"
echo "================================================================================"
echo ""
echo "1. Log in to CaseScope web interface"
echo "2. Navigate to Case 2 → IOCs tab"
echo "3. Click 'Bulk Re-Hunt IOCs' button"
echo "4. Monitor progress: journalctl -u casescope-worker -f | grep -i 'hunt\|ioc'"
echo "5. Check IOC match counts in the IOCs table"
echo ""
echo "Expected: All IOCs should now show match counts > 0"
echo ""
echo "================================================================================"

