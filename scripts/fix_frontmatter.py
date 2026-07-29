#!/usr/bin/env python3
"""Fix frontmatter that was corrupted by clean_text joining YAML lines."""
import re
import glob
import os

RAW_DIR = os.path.expanduser("~/Vaults/Wiki/raw")

# All HBR files we just created
files = sorted(glob.glob(os.path.join(RAW_DIR, "hbr-*.md")))
# Exclude pre-existing hbr-pm-* and hbr-guide-* files
files = [f for f in files if not os.path.basename(f).startswith("hbr-pm-")
         and not os.path.basename(f).startswith("hbr-guide-")]

fixed = 0
for filepath in files:
    with open(filepath, 'r') as f:
        content = f.read()

    # Find the frontmatter section
    if not content.startswith('---'):
        print(f"SKIP (no frontmatter): {os.path.basename(filepath)}")
        continue

    # Split at the closing ---
    parts = content.split('---', 2)
    if len(parts) < 3:
        print(f"SKIP (malformed): {os.path.basename(filepath)}")
        continue

    fm = parts[1]
    body = parts[2]

    # Fix known join patterns in frontmatter
    # title: "..." authors: -> title: "..."\nauthors:
    fm = re.sub(r'" authors:', '"\nauthors:', fm)
    # year: NNNN url: -> year: NNNN\nurl:
    fm = re.sub(r'(year: \d*) url:', r'\1\nurl:', fm)
    # url: publisher: -> url:\npublisher:
    fm = re.sub(r'(url:.*?) publisher:', r'\1\npublisher:', fm)
    # publisher: Harvard Business Review status: -> ...\nstatus:
    fm = re.sub(r'(publisher: .*?) status:', r'\1\nstatus:', fm)
    # status: chapter topics: -> ...\ntopics:
    fm = re.sub(r'(status: \w+) topics:', r'\1\ntopics:', fm)
    # type: article tags: -> ...\ntags:
    fm = re.sub(r'(type: \w+) tags:', r'\1\ntags:', fm)
    # parent_work: "..." clipped: -> ...\nclipped:
    fm = re.sub(r'(\]\]"\)) clipped:', r'\1\nclipped:', fm)
    # Also handle collection file which may not have parent_work
    fm = re.sub(r'(source_of:.*?) clipped:', r'\1\nclipped:', fm)
    # clipped: 2026-04-06 clipped_by: -> ...\nclipped_by:
    fm = re.sub(r'(clipped: [\d-]+) clipped_by:', r'\1\nclipped_by:', fm)
    # isbn: publisher:
    fm = re.sub(r'(isbn:.*?) publisher:', r'\1\npublisher:', fm)
    # status: complete topics:
    fm = re.sub(r'(status: complete) topics:', r'\1\ntopics:', fm)
    # type: book tags:
    fm = re.sub(r'(type: book) tags:', r'\1\ntags:', fm)
    # tags array items that got joined with source_of
    fm = re.sub(r'(- [\w-]+) source_of:', r'\1\nsource_of:', fm)

    new_content = '---' + fm + '---' + body

    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        fixed += 1
        print(f"FIXED: {os.path.basename(filepath)}")
    else:
        print(f"OK: {os.path.basename(filepath)}")

print(f"\nFixed {fixed} files out of {len(files)}")
