# Troubleshooting Document Indexing

If you're getting responses like "I don't have information about..." when querying the chat interface, it likely means documents haven't been indexed into Azure Search, or the search isn't finding relevant content.

## Quick Diagnostic

Run the verification script to check your index:

```bash
./scripts/verify_index.sh
```

This script will:
- Check if the index exists
- Count total documents indexed
- List all source files in the index
- Specifically check for Northwind Health Plus documents
- Search for "Northwind Health Plus" content
- Verify Document Intelligence configuration

## Common Issues and Solutions

### Issue 1: No Documents Indexed

**Symptoms:**
- Verification script shows "Total documents indexed: 0"
- Chat returns "I don't have information..."

**Solution:**
Index documents from the `data/` folder:

```bash
# Index all documents in data/ folder
./scripts/prepdocs.sh

# Or on Windows
scripts\prepdocs.ps1
```

This will:
1. Create the search index if it doesn't exist
2. Process all files in `data/` folder
3. Upload them to blob storage
4. Index them into Azure Search

### Issue 2: Specific Files Missing

**Symptoms:**
- Verification script shows some files but not others
- Missing files like `Northwind_Health_Plus_Benefits_Details.pdf`

**Solution:**
1. Verify files exist in `data/` folder:
   ```bash
   ls -lh data/*.pdf
   ```

2. Re-index all documents:
   ```bash
   # Remove all existing documents and re-index
   ./scripts/prepdocs.sh --removeall
   ./scripts/prepdocs.sh
   ```

3. Or index specific files:
   ```bash
   ./scripts/prepdocs.sh './data/Northwind_Health_Plus_Benefits_Details.pdf'
   ./scripts/prepdocs.sh './data/Northwind_Standard_Benefits_Details.pdf'
   ```

### Issue 3: Documents Indexed But Search Returns No Results

**Symptoms:**
- Verification shows documents are indexed
- But search for "Northwind Health Plus" returns 0 results
- Chat still says "I don't have information..."

**Possible Causes:**

1. **PDF Parsing Issues**
   - PDFs may not have been parsed correctly
   - Text extraction may have failed

2. **Search Query Issues**
   - The search query may need adjustment
   - Try different search terms

3. **Index Corruption**
   - Index may need to be rebuilt

**Solution:**

1. Check if PDFs are being parsed:
   ```bash
   # Re-index with verbose logging
   ./scripts/prepdocs.sh --verbose
   ```

2. Check Document Intelligence configuration:
   - If `USE_LOCAL_PDF_PARSER=true`, PDFs use PyMuPDF (may miss some content)
   - If Document Intelligence is configured, it should parse PDFs better
   - Check `AZURE_DOCUMENTINTELLIGENCE_SERVICE` environment variable

3. Rebuild the index:
   ```bash
   # Remove all and re-index
   ./scripts/prepdocs.sh --removeall
   ./scripts/prepdocs.sh
   ```

### Issue 4: Document Intelligence Not Working

**Symptoms:**
- PDFs aren't being parsed correctly
- Complex PDFs (with tables, images) aren't indexed properly

**Check Configuration:**

1. Verify Document Intelligence service is configured:
   ```bash
   azd env get-value AZURE_DOCUMENTINTELLIGENCE_SERVICE
   ```

2. Check if local parser is being used instead:
   ```bash
   azd env get-value USE_LOCAL_PDF_PARSER
   ```
   - If `true`, Document Intelligence is disabled
   - Set to `false` or unset to use Document Intelligence

3. Ensure Document Intelligence service exists:
   - Check Azure Portal for Cognitive Services account
   - Verify it's in the same resource group
   - Check service name matches `AZURE_DOCUMENTINTELLIGENCE_SERVICE`

**Solution:**

1. If Document Intelligence isn't configured, set it up:
   ```bash
   # Set the service name (replace with your actual service name)
   azd env set AZURE_DOCUMENTINTELLIGENCE_SERVICE "your-doc-intel-service"
   
   # Disable local parser
   azd env set USE_LOCAL_PDF_PARSER "false"
   
   # Re-provision to apply changes
   azd provision
   ```

2. Re-index documents:
   ```bash
   ./scripts/prepdocs.sh --removeall
   ./scripts/prepdocs.sh
   ```

## Manual Verification Steps

### 1. Check Azure Portal

1. Go to Azure Portal
2. Navigate to your Azure AI Search service
3. Open the "Indexes" tab
4. Click on your index (usually `gptkbindex`)
5. Check the document count
6. Use "Search explorer" to test queries:
   ```json
   {
     "search": "*",
     "count": true,
     "top": 1,
     "facets": ["sourcefile"]
   }
   ```

### 2. Check Blob Storage

1. Go to Azure Portal
2. Navigate to your Storage Account
3. Open the container (usually `gptkbindex`)
4. Verify PDFs are uploaded
5. Check file names match what's in `data/` folder

### 3. Check Index Contents via Script

The verification script provides detailed information:

```bash
./scripts/verify_index.sh
```

Look for:
- Total document count (should be > 0)
- List of source files (should include Northwind PDFs)
- Search results for "Northwind Health Plus"

## Re-indexing Workflow

If you need to completely rebuild the index:

```bash
# 1. Remove all existing documents
./scripts/prepdocs.sh --removeall

# 2. Verify index is empty (optional)
./scripts/verify_index.sh

# 3. Re-index all documents
./scripts/prepdocs.sh

# 4. Verify documents are indexed
./scripts/verify_index.sh
```

## Environment Variables to Check

Ensure these are set correctly:

```bash
# Required
azd env get-value AZURE_SEARCH_SERVICE
azd env get-value AZURE_SEARCH_INDEX
azd env get-value AZURE_STORAGE_ACCOUNT
azd env get-value AZURE_STORAGE_CONTAINER

# Optional but recommended for PDFs
azd env get-value AZURE_DOCUMENTINTELLIGENCE_SERVICE
azd env get-value USE_LOCAL_PDF_PARSER  # Should be "false" or unset for best PDF parsing
```

## Getting Help

If issues persist:

1. Check logs from prepdocs:
   ```bash
   ./scripts/prepdocs.sh --verbose 2>&1 | tee prepdocs.log
   ```

2. Check Azure Search service logs in Azure Portal

3. Verify credentials have proper permissions:
   - Search service: Search Index Data Contributor
   - Storage account: Storage Blob Data Contributor
   - Document Intelligence: Cognitive Services User (if using)

4. Check network connectivity if using private endpoints
