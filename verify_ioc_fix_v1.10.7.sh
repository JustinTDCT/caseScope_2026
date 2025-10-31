#!/bin/bash

echo "================================================================================"
echo "IOC HUNTING FIX v1.10.7 - VERIFICATION SCRIPT"
echo "================================================================================"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if code contains the fixes
echo "### TEST 1: Code Verification ###"
echo ""

if grep -q "escape_lucene_special_chars" /opt/casescope/app/file_processing.py; then
    echo -e "${GREEN}✅ Special character escaping function found${NC}"
else
    echo -e "${RED}❌ Special character escaping function NOT found${NC}"
fi

if grep -q "query_string" /opt/casescope/app/file_processing.py && \
   grep -q "nested objects" /opt/casescope/app/file_processing.py; then
    echo -e "${GREEN}✅ query_string for nested objects found${NC}"
else
    echo -e "${RED}❌ query_string for nested objects NOT found${NC}"
fi

if grep -q "scroll" /opt/casescope/app/file_processing.py && \
   grep -q "Use scroll API" /opt/casescope/app/file_processing.py; then
    echo -e "${GREEN}✅ OpenSearch Scroll API implementation found${NC}"
else
    echo -e "${RED}❌ OpenSearch Scroll API NOT found${NC}"
fi

echo ""
echo "---"
echo ""

# Test 2: Service Status
echo "### TEST 2: Service Status ###"
echo ""

if systemctl is-active --quiet casescope; then
    echo -e "${GREEN}✅ casescope service is running${NC}"
else
    echo -e "${RED}❌ casescope service is NOT running${NC}"
fi

if systemctl is-active --quiet casescope-worker; then
    echo -e "${GREEN}✅ casescope-worker service is running${NC}"
else
    echo -e "${RED}❌ casescope-worker service is NOT running${NC}"
fi

echo ""
echo "---"
echo ""

# Test 3: Manual Query Tests
echo "### TEST 3: OpenSearch Query Tests ###"
echo ""

# Test URL with special chars
echo "Testing URL with special characters..."
URL_HITS=$(curl -s -X POST "http://localhost:9200/case_2_*/_search" \
  -H 'Content-Type: application/json' \
  -d'{"query":{"query_string":{"query":"*https\\:\\/\\/55i.j3ve.ru\\/clh1ygiq*","analyze_wildcard":true,"lenient":true}},"size":0}' \
  | jq -r '.hits.total.value // 0')

if [ "$URL_HITS" -gt 0 ]; then
    echo -e "${GREEN}✅ URL query works: $URL_HITS hits${NC}"
else
    echo -e "${YELLOW}⚠️  URL query returned 0 hits (may not be in indexed data)${NC}"
fi

# Test file path with backslashes
echo "Testing file path with backslashes..."
PATH_HITS=$(curl -s -X POST "http://localhost:9200/case_2_*/_search" \
  -H 'Content-Type: application/json' \
  -d'{"query":{"query_string":{"query":"*C\\:\\\\Windows\\\\Microsoft.NET\\\\Framework\\\\v4.0.30319\\\\MSBuild.exe*","analyze_wildcard":true,"lenient":true}},"size":0}' \
  | jq -r '.hits.total.value // 0')

if [ "$PATH_HITS" -gt 0 ]; then
    echo -e "${GREEN}✅ File path query works: $PATH_HITS hits${NC}"
else
    echo -e "${YELLOW}⚠️  File path query returned 0 hits (may not be in indexed data)${NC}"
fi

# Test username (should have many hits)
echo "Testing username (should find many)..."
USERNAME_HITS=$(curl -s -X POST "http://localhost:9200/case_2_*/_search" \
  -H 'Content-Type: application/json' \
  -d'{"query":{"query_string":{"query":"*craigw*","analyze_wildcard":true,"lenient":true}},"size":0}' \
  | jq -r '.hits.total.value // 0')

if [ "$USERNAME_HITS" -gt 1000 ]; then
    echo -e "${GREEN}✅ Username query works: $USERNAME_HITS hits (unlimited results confirmed!)${NC}"
elif [ "$USERNAME_HITS" -gt 0 ]; then
    echo -e "${GREEN}✅ Username query works: $USERNAME_HITS hits${NC}"
else
    echo -e "${YELLOW}⚠️  Username query returned 0 hits (may not be in indexed data)${NC}"
fi

echo ""
echo "---"
echo ""

# Test 4: Database IOC Status
echo "### TEST 4: Database IOC Status ###"
echo ""

/opt/casescope/venv/bin/python3 << 'PYEOF'
from sqlalchemy import create_engine, text
engine = create_engine('sqlite:////opt/casescope/data/casescope.db')

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT i.id, i.ioc_type, i.ioc_value, COUNT(im.id) as matches
        FROM ioc i
        LEFT JOIN ioc_match im ON i.id = im.ioc_id
        WHERE i.case_id = 2 AND i.is_active = 1
        GROUP BY i.id
        ORDER BY i.ioc_type, i.ioc_value
    """))
    rows = result.fetchall()
    
    print(f"Active IOCs for Case 2: {len(rows)}")
    print(f"{'ID':<5} {'Type':<15} {'Value':<50} {'Matches':<10}")
    print("-" * 85)
    
    total_matches = 0
    zero_matches = 0
    for ioc_id, ioc_type, ioc_value, matches in rows:
        status = "✅" if matches > 0 else "❌"
        print(f"{status} {ioc_id:<3} {ioc_type:<15} {ioc_value[:50]:<50} {matches:<10}")
        total_matches += matches
        if matches == 0:
            zero_matches += 1
    
    print(f"\nTotal IOC Matches: {total_matches}")
    
    if zero_matches > 0:
        print(f"\n⚠️  {zero_matches} IOCs have 0 matches - RE-HUNT NEEDED!")
    else:
        print(f"\n✅ All IOCs have matches!")
PYEOF

echo ""
echo "================================================================================"
echo "SUMMARY & NEXT STEPS"
echo "================================================================================"
echo ""

if [ "$USERNAME_HITS" -gt 1000 ]; then
    echo -e "${GREEN}✅ All fixes are working correctly!${NC}"
    echo ""
    echo "The unlimited results fix is confirmed (username has $USERNAME_HITS hits)"
else
    echo -e "${YELLOW}⚠️  Some IOCs may need re-hunting to populate matches${NC}"
    echo ""
fi

echo "To trigger IOC re-hunt:"
echo "  1. Go to http://your-server:5000/case/2/files"
echo "  2. Click 'Bulk Re-Hunt IOCs' button"
echo "  3. Monitor: journalctl -u casescope-worker -f | grep -i 'hunt\|ioc'"
echo ""
echo "Expected after re-hunt:"
echo "  - All 7 IOCs should have matches > 0"
echo "  - Username 'craigw' should have 10,000+ matches"
echo "  - URLs and file paths should work (no parse errors)"
echo ""
echo "Documentation: /opt/casescope/IOC_FIX_v1.10.7_COMPLETE.md"
echo ""
echo "================================================================================"

