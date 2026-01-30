#!/bin/sh
# Force re-indexing by removing MD5 hash files and re-running prepdocs

echo "Removing MD5 hash files to force re-indexing..."
find data -name "*.md5" -type f -delete
echo "MD5 files removed."

echo ""
echo "Re-indexing all documents..."
./scripts/prepdocs.sh

echo ""
echo "Verifying index..."
./scripts/verify_index.sh
