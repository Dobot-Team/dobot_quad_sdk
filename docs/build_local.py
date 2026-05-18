"""
Build static docs that work with file:// protocol (local browsing).

Usage:
    python build_local.py

This script:
1. Runs `mkdocs build` to generate the site
2. Post-processes all HTML files to convert absolute paths (/zh/, /) to relative paths
   so the site works when opened directly from a file browser.
"""

import os
import re
import subprocess
import sys


def fix_absolute_paths(site_dir):
    """Convert absolute paths in HTML files to relative paths for local file browsing."""
    fixed = 0

    for root, dirs, files in os.walk(site_dir):
        for filename in files:
            if not filename.endswith(".html"):
                continue

            filepath = os.path.join(root, filename)
            rel_depth = os.path.relpath(site_dir, root)
            # On Windows, os.path.relpath uses backslashes
            rel_depth = rel_depth.replace("\\", "/")

            if rel_depth == ".":
                prefix = ""  # file is at site root
            else:
                prefix = rel_depth + "/"  # e.g. "../" or "../../"

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            new_content = content
            # Fix: href="/..." -> href="<relative>..."
            new_content = re.sub(r'(href=")/', rf'\1{prefix}', new_content)
            # Fix: src="/..." -> src="<relative>..."
            new_content = re.sub(r'(src=")/', rf'\1{prefix}', new_content)

            # Fix: href="zh/" -> href="zh/index.html"
            # file:// protocol does not auto-resolve directory paths to index.html
            def _append_index(match):
                url = match.group(2)
                if "://" in url:  # skip external URLs
                    return match.group(0)
                return f'{match.group(1)}{url}/index.html"'

            new_content = re.sub(r'(href=")([^"]+)/"', _append_index, new_content)

            # Fix: href="." or href="../.." -> href="./index.html" or href="../../index.html"
            # mkdocs-material uses dot-only paths for the home link; file:// can't resolve
            # directories to index.html.
            def _fix_dot_path(match):
                url = match.group(2)
                return f'{match.group(1)}{url}/index.html"'

            new_content = re.sub(
                r'(href=")(\.{1,2}(?:/\.{2})*)(?<!/)"', _fix_dot_path, new_content
            )

            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                fixed += 1
                print(f"  Fixed: {os.path.relpath(filepath, site_dir)}")

    return fixed


def main():
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(docs_dir)

    # Step 1: Build with mkdocs
    print(">>> mkdocs build")
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(1)

    site_dir = os.path.join(docs_dir, "site")

    # Step 2: Fix absolute paths
    print(">>> Fixing absolute paths for local file browsing...")
    count = fix_absolute_paths(site_dir)
    print(f">>> Done. Fixed {count} file(s).")
    print(f">>> Open {os.path.join(site_dir, 'index.html')} in your browser.")


if __name__ == "__main__":
    main()
