#!/usr/bin/env python3
"""
Simple test script for the email generation API.

This script tests the complete flow:
1. POST /api/email/generate - Enqueue email generation
2. GET /api/email/status/{task_id} - Poll for completion
3. GET /api/email/{email_id} - Retrieve generated email
4. GET /api/email/ - View email history

Usage:
    python tests/integration/test_email_api.py
"""

import os
import time
import requests
from typing import Dict, Any


# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://scribeserver.onrender.com")
JWT_TOKEN = os.getenv("JWT_TOKEN", "")

# ANSI color codes for pretty output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_step(step: str, message: str):
    """Print a colored step message."""
    print(f"\n{BLUE}[{step}]{RESET} {message}")


def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✓{RESET} {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"{RED}✗{RESET} {message}")


def print_info(message: str):
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
        "Content-Type": "application/json"
    }


def test_user_init() -> bool:
    """Test user initialization (idempotent)."""
    print_step("STEP 0", "Initializing user profile...")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/user/init",
            headers=get_headers()
        )

        if response.status_code in [200, 201]:
            user_data = response.json()
            print_success(f"User initialized: {user_data.get('email')}")
            return True
        else:
            print_error(f"User init failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print_error(f"User init error: {str(e)}")
        return False


def test_generate_email() -> str | None:
    """Test email generation endpoint. Returns task_id if successful."""
    print_step("STEP 1", "Generating email...")

    # Sample request payload
    payload = {
        "email_template": (
            "Hey {{name}},\n\n"
            "I just finished going through your {{research}} work, especially the section on {{recent_publication_title}}, and it sparked a dozen ideas on the train ride home."
            " I'm fascinated by how you're coordinating things at {{lab_name}} and would love to compare notes on how you're approaching {{specific_problem}}.\n\n"
            "Here's why I think a quick collaboration chat could be fun:\n"
            "• I'm currently prototyping a lightweight workflow for {{shared_goal}} and would value your take on where the real bottlenecks are.\n"
            "• Your insights from {{recent_talk_or_event}} line up eerily well with what my team has been seeing in the field.\n"
            "• I have access to a small pilot group eager to try anything connected to {{application_area}}, so we could pressure-test ideas fast.\n\n"
            "If you're open to it, could we grab {{preferred_call_length}} sometime next week?"
            " Happy to accommodate whatever time zone you're juggling. I can also share a short brief before we chat so you can see if it's worth the time.\n\n"
            "Either way, thanks for all the generous writing you've put out—{{standout_takeaway}} has already nudged how I'm framing our internal roadmap.\n\n"
            "Talk soon,\n"
            "{{sender_signature}}"
        ),
        "recipient_name": "Andrew Ng",
        "recipient_interest": "machine learning",
        "template_type": "research"
    }

    print_info(f"Request payload:")
    print(f"  • Recipient: {payload['recipient_name']}")
    print(f"  • Interest: {payload['recipient_interest']}")
    print(f"  • Template type: {payload['template_type']}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/email/generate",
            headers=get_headers(),
            json=payload
        )

        if response.status_code == 202:
            data = response.json()
            task_id = data.get("task_id")
            print_success(f"Email generation enqueued! Task ID: {task_id}")
            return task_id
        else:
            print_error(f"Generate failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print_error(f"Generate error: {str(e)}")
        return None


def test_poll_status(task_id: str, max_wait: int = 180) -> Dict[str, Any] | None:
    """Poll task status until completion or timeout. Returns final result."""
    print_step("STEP 2", f"Polling task status (max {max_wait}s)...")

    start_time = time.time()
    poll_count = 0

    while time.time() - start_time < max_wait:
        poll_count += 1

        try:
            response = requests.get(
                f"{API_BASE_URL}/api/email/status/{task_id}",
                headers=get_headers()
            )

            if response.status_code != 200:
                print_error(f"Status check failed: {response.status_code}")
                return None

            data = response.json()
            status = data.get("status")

            # Print current status
            if status == "PENDING":
                print_info(f"Poll #{poll_count}: Task queued, waiting for worker...")

            elif status == "STARTED":
                result = data.get("result", {})
                current_step = result.get("current_step", "unknown")
                step_status = result.get("step_status", "unknown")
                print_info(f"Poll #{poll_count}: Running - {current_step} ({step_status})")

            elif status == "SUCCESS":
                result = data.get("result", {})
                email_id = result.get("email_id")
                elapsed = time.time() - start_time
                print_success(f"Task completed in {elapsed:.1f}s! Email ID: {email_id}")
                return result

            elif status == "FAILURE":
                error = data.get("error", "Unknown error")
                print_error(f"Task failed: {error}")
                return None

            # Wait before next poll
            time.sleep(2)

        except Exception as e:
            print_error(f"Polling error: {str(e)}")
            return None

    print_error(f"Timeout after {max_wait}s")
    return None


def test_get_email(email_id: str) -> Dict[str, Any] | None:
    """Test retrieving a generated email."""
    print_step("STEP 3", f"Retrieving email...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/email/{email_id}",
            headers=get_headers()
        )

        if response.status_code == 200:
            email = response.json()
            print_success(f"Email retrieved successfully!")
            print("\n" + "="*70)
            print(f"To: {email.get('recipient_name')}")
            print(f"Interest: {email.get('recipient_interest')}")
            print(f"Template Type: {email.get('template_type')}")
            print(f"Created: {email.get('created_at')}")
            print("="*70)
            print("\nEmail Content:")
            print("-"*70)
            print(email.get('email_message', 'No content'))
            print("-"*70)

            # Show metadata if available
            if email.get('metadata'):
                print("\nMetadata:")
                metadata = email['metadata']
                for key, value in metadata.items():
                    print(f"  • {key}: {value}")

            return email
        else:
            print_error(f"Get email failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print_error(f"Get email error: {str(e)}")
        return None


def test_email_history() -> list | None:
    """Test retrieving email history."""
    print_step("STEP 4", "Retrieving email history...")

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/email/?limit=5",
            headers=get_headers()
        )

        if response.status_code == 200:
            emails = response.json()
            print_success(f"Found {len(emails)} emails in history")

            if emails:
                print("\nRecent emails:")
                for i, email in enumerate(emails, 1):
                    print(f"  {i}. {email.get('recipient_name')} - {email.get('created_at')}")

            return emails
        else:
            print_error(f"History failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print_error(f"History error: {str(e)}")
        return None


def main():
    """Run the complete test suite."""
    print("="*70)
    print("EMAIL GENERATION API - INTEGRATION TEST")
    print("="*70)
    print(f"\nAPI Base URL: {API_BASE_URL}")
    print(f"JWT Token: {'✓ Set' if JWT_TOKEN else '✗ Not set'}")

    # Step 0: Initialize user
    if not test_user_init():
        print_error("\nTest aborted: User initialization failed")
        return

    # Step 1: Generate email
    task_id = test_generate_email()
    if not task_id:
        print_error("\nTest aborted: Email generation failed")
        return

    # Step 2: Poll for completion
    result = test_poll_status(task_id)
    if not result:
        print_error("\nTest aborted: Task polling failed or timed out")
        return

    email_id = result.get("email_id")
    if not email_id:
        print_error("\nTest aborted: No email_id in result")
        return

    # Step 3: Retrieve email
    email = test_get_email(email_id)
    if not email:
        print_error("\nTest aborted: Email retrieval failed")
        return

    # Step 4: View history
    test_email_history()

    # Summary
    print("\n" + "="*70)
    print(f"{GREEN}✓ ALL TESTS PASSED!{RESET}")
    print("="*70)
    print("\nNext steps:")
    print("  • Check Flower UI: http://localhost:5555")
    print("  • Check Logfire dashboard for distributed traces")
    print("  • Try different template types: 'book' or 'general'")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Test interrupted by user{RESET}")
    except Exception as e:
        print_error(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
