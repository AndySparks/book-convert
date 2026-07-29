#!/usr/bin/env python3
"""Fix parent_work line that has clipped: joined on same line."""
import re
import glob
import os

RAW_DIR = os.path.expanduser("~/Vaults/Wiki/raw")
files = sorted(glob.glob(os.path.join(RAW_DIR, "hbr-*.md")))
files = [f for f in files if not os.path.basename(f).startswith("hbr-pm-")
         and not os.path.basename(f).startswith("hbr-guide-")]

fixed = 0
for filepath in files:
    with open(filepath, 'r') as f:
        content = f.read()

    # Fix: parent_work: "[[...]]" clipped: -> separate lines
    new_content = re.sub(
        r'(parent_work: "\[\[.*?\]\]")\s+(clipped:)',
        r'\1\n\2',
        content
    )

    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        fixed += 1

print(f"Fixed {fixed} files")
