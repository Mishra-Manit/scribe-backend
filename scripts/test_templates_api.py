#!/usr/bin/env python3
"""
Simple test script for the template generation API.

This script tests the complete flow for the new template feature:

1. POST /api/templates/           - Generate templates (up to the per-user limit)
2. GET  /api/templates/           - List templates
3. GET  /api/templates/{id}       - Fetch a single template
4. GET  /api/user/resume-url      - Verify constructed resume URL
5. GET  /api/user/profile         - Optionally inspect template_count (if exposed)

Usage:
    python test_templates_api.py

Make sure your FastAPI server is running and JWT_TOKEN is valid for
`API_BASE_URL`.
"""

import os
import time
from typing import Dict, Any, List, Optional

import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://scribeserver.onrender.com")
JWT_TOKEN = os.getenv("JWT_TOKEN", "")

# ANSI color codes for pretty output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_step(step: str, message: str) -> None:
    """Print a colored step message."""
    print(f"\n{BLUE}[{step}]{RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{GREEN}✓{RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{RED}✗{RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{YELLOW}ℹ{RESET} {message}")


def get_headers() -> Dict[str, str]:
    """Get request headers with JWT token."""
    if not JWT_TOKEN:
        raise ValueError(
            "JWT_TOKEN environment variable not set!\n"
            "Get a token from Supabase and run:\n"
            "  export JWT_TOKEN='your-token-here'"
        )

    return {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
    }


def test_user_init() -> bool:
    """Ensure user profile exists (idempotent)."""
    print_step("STEP 0", "Initializing user profile (if needed)...")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/user/init", headers=get_headers()
        )

        if response.status_code in (200, 201):
            user_data = response.json()
            print_success(f"User initialized: {user_data.get('email')}")
            return True

        print_error(
            f"User init failed: {response.status_code} - {response.text}"
        )
        return False

    except Exception as exc:  # noqa: BLE001
        print_error(f"User init error: {exc}")
        return False


def test_resume_url() -> Optional[str]:
    """Call GET /api/user/resume-url and show the constructed URL."""
    print_step("STEP 1", "Fetching resume URL...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/user/resume-url", headers=get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            resume_url = data.get("resume_url")
            if resume_url:
                print_success(f"Resume URL: {resume_url}")
            else:
                print_error("resume_url field missing in response")
            return resume_url

        print_error(
            f"Resume URL failed: {response.status_code} - {response.text}"
        )
        return None

    except Exception as exc:  # noqa: BLE001
        print_error(f"Resume URL error: {exc}")
        return None


def build_sample_payload(index: int) -> Dict[str, Any]:
    """Build a sample generate-template payload varying by index."""
    return {
        "resume_url": "https://writing.colostate.edu/guides/documents/resume/functionalsample.pdf",  # adjust if needed
        "target_role": f"Research Scientist {index}",
        "target_company": f"Example Lab {index}",
        "job_description": (
            "We are looking for a research scientist with strong ML background, "
            "experience in LLMs, and a track record of publishing at top venues."
        ),
        # This can be extended as your GenerateTemplateRequest evolves
    }


def test_generate_template(idx: int = 1) -> Optional[int]:
    """Generate a single template and return its ID if created."""
    print_step("STEP 2", f"Generating template #{idx}...")

    payload = build_sample_payload(idx)
    print_info(
        "Payload summary: "
        f"role={payload['target_role']}, company={payload['target_company']}"
    )

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/templates/", headers=get_headers(), json=payload
        )

        if response.status_code == 201:
            data = response.json()
            template_id = data.get("id")
            print_success(f"Template #{idx} created with id={template_id}")
            return template_id

        print_error(
            "Generate template failed: "
            f"{response.status_code} - {response.text}"
        )
        return None

    except Exception as exc:  # noqa: BLE001
        print_error(f"Generate template error: {exc}")
        return None


def test_generate_templates_up_to_limit(limit: int = 5) -> List[int]:
    """Attempt to create templates up to the configured per-user limit.

    Also tries one extra creation to verify the 429 response when the limit
    is exceeded.
    """
    print_step("STEP 3", f"Creating up to {limit} templates (then one extra)...")

    created_ids: List[int] = []

    # Create up to the limit
    for i in range(1, limit + 1):
        template_id = test_generate_template(i)
        if template_id is not None:
            created_ids.append(template_id)
        else:
            print_error(f"Stopping early: failed to create template #{i}")
            return created_ids

    # Attempt one more to verify limit enforcement
    print_step("STEP 3B", "Attempting to exceed template limit...")
    payload = build_sample_payload(limit + 1)

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/templates/", headers=get_headers(), json=payload
        )

        if response.status_code == 429:
            print_success(
                "Limit enforcement worked: received 429 Too Many Requests"
            )
        else:
            print_error(
                "Expected 429 when exceeding limit, got "
                f"{response.status_code} - {response.text}"
            )

    except Exception as exc:  # noqa: BLE001
        print_error(f"Limit test error: {exc}")

    return created_ids


def test_list_templates() -> List[Dict[str, Any]]:
    """List templates and return the parsed list."""
    print_step("STEP 4", "Listing templates...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/templates/?limit=10", headers=get_headers()
        )

        if response.status_code == 200:
            templates = response.json()
            count = len(templates)
            print_success(f"Retrieved {count} templates")
            for idx, item in enumerate(templates, start=1):
                print(
                    f"  {idx}. id={item.get('id')} role={item.get('target_role')} "
                    f"company={item.get('target_company')}"
                )
            return templates

        print_error(
            f"List templates failed: {response.status_code} - {response.text}"
        )
        return []

    except Exception as exc:  # noqa: BLE001
        print_error(f"List templates error: {exc}")
        return []


def test_get_template(template_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single template by ID."""
    print_step("STEP 5", f"Fetching template id={template_id}...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/templates/{template_id}", headers=get_headers()
        )

        if response.status_code == 200:
            template = response.json()
            print_success(
                "Template fetched: "
                f"role={template.get('target_role')}, "
                f"company={template.get('target_company')}"
            )
            # Print a short preview of the generated template if present
            body = template.get("generated_template") or template.get("body")
            if body:
                print("\n--- Template Preview (first 400 chars) ---")
                print(str(body)[:400])
                print("\n-----------------------------------------")
            return template

        print_error(
            f"Get template failed: {response.status_code} - {response.text}"
        )
        return None

    except Exception as exc:  # noqa: BLE001
        print_error(f"Get template error: {exc}")
        return None



def test_user_profile() -> None:
    """Optionally inspect /api/user/profile for template_count, if exposed."""
    print_step("STEP 7", "Fetching user profile (optional template_count check)...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/user/profile", headers=get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            template_count = data.get("template_count")
            if template_count is not None:
                print_success(f"User template_count: {template_count}")
            else:
                print_info("template_count not present in profile response")
        else:
            print_error(
                f"User profile failed: {response.status_code} - {response.text}"
            )

    except Exception as exc:  # noqa: BLE001
        print_error(f"User profile error: {exc}")


def main() -> None:
    """Run the complete template feature test suite."""
    print("=" * 70)
    print("TEMPLATE GENERATION API - INTEGRATION TEST")
    print("=" * 70)
    print(f"\nAPI Base URL: {API_BASE_URL}")
    print(f"JWT Token: {'✓ Set' if JWT_TOKEN else '✗ Not set'}")

    # Step 0: Ensure user exists
    if not test_user_init():
        print_error("\nTest aborted: User initialization failed")
        return

    # Step 1: Check resume URL construction
    test_resume_url()

    # Step 2–3: Create templates up to limit and verify limit enforcement
    created_ids = test_generate_templates_up_to_limit(limit=5)
    if not created_ids:
        print_error("\nTest aborted: No templates created")
        return

    # Small pause before listing
    time.sleep(1)

    # Step 4: List templates
    all_templates = test_list_templates()

    # Step 5: Fetch one of the created templates
    first_id = created_ids[0]
    template = test_get_template(first_id)
    if not template:
        print_error("\nWarning: Failed to fetch first created template")

    # Step 6: Optional profile check for template_count
    test_user_profile()

    # Summary
    print("\n" + "=" * 70)
    print(f"{GREEN}✓ TEMPLATE FEATURE TESTS COMPLETED{RESET}")
    print("=" * 70)
    print("\nNext steps:")
    print("  • Inspect FastAPI /docs for schema details")
    print("  • Review server logs / Logfire traces for errors")
    print("  • Adjust payload fields as GenerateTemplateRequest evolves")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Test interrupted by user{RESET}")
    except Exception as exc:  # noqa: BLE001
        print_error(f"\nUnexpected error: {exc}")
        import traceback

        traceback.print_exc()
