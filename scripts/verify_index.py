#!/usr/bin/env python3
"""
Verify Azure Search index contents and configuration.
Checks if documents are indexed and provides diagnostic information.

Usage:
    python scripts/verify_index.py
"""

import asyncio
import json
import logging
import os
import ssl
import sys
from collections import Counter
from pathlib import Path

# Configure SSL certificates for macOS compatibility
# This ensures Azure SDK can verify SSL certificates
try:
    import certifi
    
    # Set SSL certificate file environment variable
    # This helps httpx and requests find the certificate bundle
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    
    # Configure Python's default SSL context to use certifi's certificates
    # This ensures SSL verification works on macOS where system certificates may not be accessible
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # certifi should be installed, but handle gracefully if not
    pass

# Add app/backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "backend"))

from azure.identity.aio import AzureDeveloperCliCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from dotenv import load_dotenv

# Try to load azd env
try:
    from load_azd_env import load_azd_env
    load_azd_env()
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("verify_index")


async def verify_search_index():
    """Verify Azure Search index contents and configuration."""
    
    # Get environment variables
    search_service = os.environ.get("AZURE_SEARCH_SERVICE")
    index_name = os.environ.get("AZURE_SEARCH_INDEX")
    
    if not search_service or not index_name:
        logger.error("Missing required environment variables:")
        logger.error(f"  AZURE_SEARCH_SERVICE: {search_service}")
        logger.error(f"  AZURE_SEARCH_INDEX: {index_name}")
        logger.error("\nPlease ensure you have loaded the azd environment or set these variables.")
        sys.exit(1)
    
    endpoint = f"https://{search_service}.search.windows.net"
    logger.info(f"Connecting to Azure Search: {search_service}")
    logger.info(f"Index name: {index_name}")
    
    # Use Azure credential
    tenant_id = os.getenv("AZURE_TENANT_ID")
    if tenant_id:
        credential = AzureDeveloperCliCredential(tenant_id=tenant_id, process_timeout=60)
    else:
        credential = AzureDeveloperCliCredential(process_timeout=60)
    
    try:
        # Check index exists and get its configuration
        async with SearchIndexClient(endpoint=endpoint, credential=credential) as index_client:
            try:
                index = await index_client.get_index(index_name)
                logger.info(f"✓ Index '{index_name}' exists")
                logger.info(f"  Fields: {len(index.fields)}")
                logger.info(f"  Vector search: {'Yes' if index.vector_search else 'No'}")
                logger.info(f"  Semantic search: {'Yes' if index.semantic_search else 'No'}")
            except Exception as e:
                logger.error(f"✗ Index '{index_name}' not found or inaccessible: {e}")
                logger.error("  Run 'scripts/prepdocs.sh' to create and populate the index.")
                sys.exit(1)
        
        # Query the index to check document count and source files
        async with SearchClient(endpoint=endpoint, index_name=index_name, credential=credential) as search_client:
            # Get total document count
            result = await search_client.search(search_text="*", top=0, include_total_count=True)
            total_count = await result.get_count()
            logger.info(f"\n✓ Total documents indexed: {total_count}")
            
            if total_count == 0:
                logger.warning("\n⚠️  WARNING: No documents found in the index!")
                logger.warning("  Run 'scripts/prepdocs.sh' to index documents from the data folder.")
                return
            
            # Get sample documents to check source files
            logger.info("\nFetching document samples to check source files...")
            result = await search_client.search(
                search_text="*",
                top=1000,
                include_total_count=True,
                select=["id", "sourcefile", "sourcepage", "category"]
            )
            
            source_files = []
            async for doc in result:
                if "sourcefile" in doc:
                    source_files.append(doc["sourcefile"])
            
            # Count occurrences of each source file
            file_counts = Counter(source_files)
            
            logger.info(f"\n✓ Found {len(file_counts)} unique source files:")
            for filename, count in sorted(file_counts.items()):
                logger.info(f"  - {filename}: {count} chunks")
            
            # Check for Northwind files specifically
            logger.info("\n" + "="*60)
            logger.info("Checking for Northwind Health Plus documents:")
            logger.info("="*60)
            
            northwind_files = [
                "Northwind_Health_Plus_Benefits_Details.pdf",
                "Northwind_Standard_Benefits_Details.pdf"
            ]
            
            found_files = []
            missing_files = []
            
            for filename in northwind_files:
                if filename in file_counts:
                    found_files.append(filename)
                    logger.info(f"✓ Found: {filename} ({file_counts[filename]} chunks)")
                else:
                    missing_files.append(filename)
                    logger.warning(f"✗ Missing: {filename}")
            
            if missing_files:
                logger.warning(f"\n⚠️  Missing files: {', '.join(missing_files)}")
                logger.warning("  These files may not have been indexed.")
                logger.warning("  Check:")
                logger.warning("    1. Files exist in the data/ folder")
                logger.warning("    2. Run 'scripts/prepdocs.sh' to index them")
            
            # Search for Northwind content
            logger.info("\n" + "="*60)
            logger.info("Searching for 'Northwind Health Plus' content:")
            logger.info("="*60)
            
            search_result = await search_client.search(
                search_text="Northwind Health Plus",
                top=5,
                include_total_count=True,
                select=["id", "sourcefile", "sourcepage", "content"]
            )
            
            match_count = await search_result.get_count()
            logger.info(f"Found {match_count} matching chunks")
            
            if match_count > 0:
                logger.info("\nSample matches:")
                async for doc in search_result:
                    content_preview = doc.get("content", "")[:200]
                    logger.info(f"  - {doc.get('sourcefile')} (page {doc.get('sourcepage')}): {content_preview}...")
            else:
                logger.warning("✗ No content found matching 'Northwind Health Plus'")
                logger.warning("  This suggests the documents may not be properly indexed.")
            
            # Check Document Intelligence configuration
            logger.info("\n" + "="*60)
            logger.info("Document Intelligence Configuration:")
            logger.info("="*60)
            
            doc_int_service = os.getenv("AZURE_DOCUMENTINTELLIGENCE_SERVICE")
            use_local_parser = os.getenv("USE_LOCAL_PDF_PARSER", "").lower() == "true"
            
            if use_local_parser:
                logger.info("✓ Using local PDF parser (PyMuPDF)")
                logger.info("  Document Intelligence is NOT being used for PDFs")
            elif doc_int_service:
                logger.info(f"✓ Document Intelligence service: {doc_int_service}")
                logger.info("  PDFs are being processed with Document Intelligence")
            else:
                logger.warning("⚠️  Document Intelligence not configured")
                logger.warning("  PDFs will be processed with local parser (PyMuPDF)")
            
            # Summary
            logger.info("\n" + "="*60)
            logger.info("Summary:")
            logger.info("="*60)
            logger.info(f"Total documents: {total_count}")
            logger.info(f"Unique source files: {len(file_counts)}")
            
            if missing_files:
                logger.warning(f"\n⚠️  ACTION REQUIRED:")
                logger.warning(f"  Missing files: {', '.join(missing_files)}")
                logger.warning(f"  Run: scripts/prepdocs.sh")
            elif match_count == 0:
                logger.warning(f"\n⚠️  ACTION REQUIRED:")
                logger.warning(f"  Documents are indexed but 'Northwind Health Plus' search returns no results")
                logger.warning(f"  This may indicate:")
                logger.warning(f"    1. Documents were not parsed correctly")
                logger.warning(f"    2. Search query needs adjustment")
                logger.warning(f"    3. Re-indexing may be needed: scripts/prepdocs.sh --removeall && scripts/prepdocs.sh")
            else:
                logger.info(f"\n✓ Index appears to be properly configured and populated")
    
    except Exception as e:
        logger.error(f"Error verifying index: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify_search_index())
