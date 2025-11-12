#!/usr/bin/env python3
import re

pattern = r'_\$[A-Z0-9]+\.[a-z]+$'
test_files = [
    'TASERVER3_$17WWJ3J.evtx',
    'TASERVER3_$IK21JKU.evtx',
    'TASERVER3_$ICQQMOG.evtx',
    'normal_file.evtx',
    'FILE_$ABC123.evtx',
    '~$document.evtx',
    'test.tmp'
]

print('Testing temp file detection:')
for f in test_files:
    is_temp = bool(re.search(pattern, f, re.IGNORECASE)) or f.startswith('~$') or f.lower().endswith('.tmp')
    print(f'{f}: {is_temp}')

