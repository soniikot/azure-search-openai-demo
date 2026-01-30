#!/usr/bin/env python3
"""
Generate Q&A pairs from documents in the data folder.
- Generates questions using Azure OpenAI
- Gets answers from the app via /chat endpoint
- Outputs JSONL file in profile_data/ suitable for HuggingFace datasets

Usage:
    python scripts/generate_qa_profile_data.py [--endpoint URL] [--count N] [--output FILE]

Environment:
    BACKEND_URI - Backend API URL (default: from .env or https://...)
    Or use --endpoint flag
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add app/backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "backend"))

from dotenv import load_dotenv
from openai import AzureOpenAI
from pypdf import PdfReader
from requests import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("generate_qa_profile")

# Suppress verbose Azure Identity/Core logs
for _logger in ("azure.identity", "azure.core", "urllib3.connectionpool"):
    logging.getLogger(_logger).setLevel(logging.WARNING)


def load_document_content(data_dir: Path) -> str:
    """Load and concatenate text content from all documents in data folder."""
    content_parts = []
    for file_path in sorted(data_dir.iterdir()):
        if file_path.is_file() and not file_path.name.startswith("."):
            try:
                if file_path.suffix.lower() == ".md":
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                elif file_path.suffix.lower() == ".pdf":
                    reader = PdfReader(file_path)
                    text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                elif file_path.suffix.lower() == ".txt":
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                else:
                    continue
                if text.strip():
                    content_parts.append(f"--- {file_path.name} ---\n{text}")
            except Exception as e:
                logger.warning(f"Could not read {file_path.name}: {e}")
    return "\n\n".join(content_parts)


def generate_questions(
    client: AzureOpenAI,
    document_content: str,
    count: int,
    deployment: str = "gpt-4o",
) -> list[str]:
    """Use Azure OpenAI to generate diverse questions based on document content."""
    # Truncate if very long (keep first ~50k chars)
    max_chars = 50000
    if len(document_content) > max_chars:
        document_content = document_content[:max_chars] + "\n\n[... truncated ...]"

    prompt = f"""Based on the following document content, generate exactly {count} diverse questions that a user might ask about this information.
Each question should be answerable from the documents. Vary the question types: factual, procedural, comparison, policy-related, etc.
Return ONLY the questions, one per line, numbered 1-{count}. No other text.

Document content:
{document_content}
"""

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "NotFound" in error_msg or "Resource not found" in error_msg:
            raise ValueError(
                f"Deployment '{deployment}' not found. "
                f"Please check your Azure OpenAI deployments or specify a different one with --deployment."
            ) from e
        raise
    
    text = response.choices[0].message.content or ""
    questions = []
    for line in text.strip().split("\n"):
        line = line.strip()
        # Remove leading number (e.g., "1. " or "1)")
        if line:
            for sep in (". ", ") ", ": "):
                if sep in line and line.split(sep)[0].strip().isdigit():
                    line = line.split(sep, 1)[1].strip()
                    break
            questions.append(line)
    return questions[:count]


def call_chat_api(
    session: Session,
    base_url: str,
    question: str,
    headers: dict | None = None,
) -> dict:
    """Call the /chat endpoint to get an answer."""
    url = f"{base_url.rstrip('/')}/chat"
    payload = {
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "context": {},
        "session_state": None
    }
    
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    
    resp = session.post(url, json=payload, headers=request_headers, timeout=120)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Generate Q&A profile data from documents"
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("BACKEND_URI"),
        help="Backend API URL (e.g., https://capps-backend-xxx.azurecontainerapps.io)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of Q&A pairs to generate (default: 100)",
    )
    parser.add_argument(
        "--output",
        default="profile_data/qa_profile_data.jsonl",
        help="Output JSONL file path (default: profile_data/qa_profile_data.jsonl)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing source documents (default: data)",
    )
    parser.add_argument(
        "--deployment",
        default=None,
        help="Azure OpenAI deployment name for question generation (default: from AZURE_OPENAI_CHATGPT_DEPLOYMENT or 'gpt-4o')",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Azure OpenAI API key (default: from AZURE_OPENAI_API_KEY environment variable)",
    )
    parser.add_argument(
        "--api-version",
        default=None,
        help="Azure OpenAI API version (default: from AZURE_OPENAI_API_VERSION or '2025-01-01-preview')",
    )
    args = parser.parse_args()

    # Load env: azd first (has BACKEND_URI), then app/backend/.env
    project_root = Path(__file__).resolve().parent.parent
    
    # Try to load azd env
    try:
        from load_azd_env import load_azd_env
        load_azd_env()
    except Exception as e:
        logger.debug(f"Could not load azd env: {e}")
    
    # Also try loading from app/backend/.env if it exists
    env_path = project_root / "app" / "backend" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    endpoint = args.endpoint
    if not endpoint:
        endpoint = os.environ.get("BACKEND_URI")
        if not endpoint:
            logger.error(
                "No endpoint specified. Set BACKEND_URI environment variable, "
                "or use --endpoint <your-backend-url>"
            )
            sys.exit(1)

    endpoint = endpoint.rstrip("/")
    if "xxx" in endpoint.lower():
        logger.error(
            "Endpoint appears to be a placeholder (contains 'xxx'). "
            "Use your actual backend URL or set BACKEND_URI environment variable."
        )
        sys.exit(1)
    logger.info(f"Using endpoint: {endpoint}")

    # Paths
    data_dir = project_root / args.data_dir
    output_path = project_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Delete file from previous run
    if output_path.exists():
        output_path.unlink()
        logger.info(f"Removed previous output: {output_path}")

    # Load documents
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    document_content = load_document_content(data_dir)
    if not document_content.strip():
        logger.error("No document content found")
        sys.exit(1)
    logger.info(f"Loaded {len(document_content)} chars from documents")

    # Initialize Azure OpenAI client for question generation
    # Command line arg takes precedence, then environment variable
    api_key = args.api_key or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY_OVERRIDE")
    api_version = args.api_version or os.environ.get("AZURE_OPENAI_API_VERSION") or "2025-01-01-preview"
    
    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        logger.error("AZURE_OPENAI_ENDPOINT environment variable is not set")
        logger.error("Set it with: azd env get-value AZURE_OPENAI_ENDPOINT")
        sys.exit(1)
    
    azure_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    logger.info(f"Azure OpenAI endpoint: {azure_endpoint}")
    logger.info(f"Azure OpenAI API version: {api_version}")
    
    if api_key:
        logger.info("Using API key authentication")
        client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint,
        )
    else:
        logger.info("Using Azure AD authentication")
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        client = AzureOpenAI(
            azure_ad_token_provider=token_provider,
            api_version=api_version,
            azure_endpoint=azure_endpoint,
        )

    # Determine deployment name - command line arg takes precedence, then env var, then default
    deployment = args.deployment or os.environ.get("AZURE_OPENAI_CHATGPT_DEPLOYMENT") or "gpt-4o"
    
    logger.info(f"Using deployment: {deployment}")
    logger.info(f"Azure OpenAI endpoint: {os.environ.get('AZURE_OPENAI_ENDPOINT', 'Not set')}")
    
    # Try to generate questions with the specified deployment
    try:
        questions = generate_questions(
            client, document_content, args.count, deployment
        )
        logger.info(f"Generated {len(questions)} questions")
    except ValueError as e:
        # Deployment not found error
        logger.error(str(e))
        logger.error("\nTo fix this:")
        logger.error("  1. Check your Azure OpenAI deployments in Azure Portal")
        logger.error("  2. Set the correct deployment name:")
        logger.error(f"     azd env set AZURE_OPENAI_CHATGPT_DEPLOYMENT <your-deployment-name>")
        logger.error("  3. Or specify it directly:")
        logger.error(f"     ./scripts/generate_qa_profile_data.sh --deployment <your-deployment-name>")
        sys.exit(1)

    # Initialize session for API calls
    session = Session()
    
    # Check if authentication is required
    # If AZURE_USE_AUTHENTICATION is set, we may need to handle auth
    # For now, we'll try without auth headers first
    headers = None
    use_auth = os.environ.get("AZURE_USE_AUTHENTICATION", "").lower() == "true"
    if use_auth:
        logger.warning(
            "Authentication is enabled. You may need to provide an auth token. "
            "The script will attempt to call the API without auth first."
        )

    records = []
    for i, question in enumerate(questions):
        if not question.strip():
            continue
        try:
            logger.info(f"[{i + 1}/{len(questions)}] Getting answer for: {question[:80]}...")
            
            # Call the /chat endpoint
            try:
                response = call_chat_api(session, endpoint, question, headers)
                
                # Extract answer from response
                # Response format: {"message": {"content": "...", "role": "assistant"}, "context": {...}, "session_state": ...}
                answer = ""
                if "message" in response and "content" in response["message"]:
                    answer = response["message"]["content"]
                elif "error" in response:
                    logger.error(f"[{i + 1}] API returned error: {response['error']}")
                    answer = ""
                else:
                    logger.warning(f"[{i + 1}] Unexpected response format. Response: {json.dumps(response)[:200]}")
                    answer = ""
                
                if not answer:
                    logger.warning(f"[{i + 1}] Empty answer received")
                    
                logger.info(f"[{i + 1}] Received answer: {len(answer)} chars")
                
            except Exception as e:
                logger.error(f"[{i + 1}] Failed to get answer from API: {e}", exc_info=True)
                answer = ""  # Fallback to empty answer on error

            # Create record
            record = {
                "id": i + 1,
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                "question": question,
                "answer": answer,
            }

            records.append(record)
            logger.info(f"[{i + 1}/{len(questions)}] Q&A recorded")

        except Exception as e:
            logger.error(f"[{i + 1}] Failed: {e}", exc_info=True)
            records.append({
                "id": i + 1,
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": ""},
                ],
                "question": question,
                "answer": "",
                "error": str(e),
            })

    # Write JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Wrote {len(records)} records to {output_path}")
    logger.info("JSONL format: messages (HuggingFace chat format), question, answer")


if __name__ == "__main__":
    main()
