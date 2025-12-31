"""
Quick performance test to verify thread pool fix eliminated blocking.

This script tests database write performance in an async context to ensure
the asyncio.to_thread() fix resolved the 400+ second blocking issue.
"""

import asyncio
import time
from uuid import uuid4

from pipeline.steps.email_composer.db_utils import write_email_to_db
from pipeline.models.core import TemplateType


async def test_concurrent_writes():
    """Test that multiple concurrent database writes don't block each other."""

    # Use a real user ID from your database or a test user
    test_user_id = uuid4()  # In production, use actual user ID

    print("Starting concurrent database write test...")
    print("This should complete in ~1-2 seconds, not 400+ seconds\n")

    async def write_single_email(index: int):
        """Write a single email and measure time."""
        start = time.time()

        email_id = await write_email_to_db(
            user_id=test_user_id,
            recipient_name=f"Test Recipient {index}",
            recipient_interest="Test interest",
            email_content="Test email content for performance testing",
            template_type=TemplateType.GENERAL,
            metadata={"test": True, "index": index},
            is_confident=True
        )

        elapsed = time.time() - start
        return email_id, elapsed

    # Run 3 concurrent writes
    start_time = time.time()

    tasks = [write_single_email(i) for i in range(3)]
    results = await asyncio.gather(*tasks)

    total_time = time.time() - start_time

    print(f"✅ Completed {len(results)} concurrent database writes")
    print(f"⏱️  Total time: {total_time:.2f} seconds")
    print(f"\nIndividual write times:")
    for i, (email_id, elapsed) in enumerate(results):
        status = "✅" if email_id else "❌"
        print(f"  {status} Write {i+1}: {elapsed:.2f}s - Email ID: {email_id}")

    if total_time < 5:
        print(f"\n🎉 SUCCESS! Database writes are no longer blocking (< 5s)")
        print("The thread pool fix is working correctly.")
    else:
        print(f"\n⚠️  WARNING: Writes took {total_time:.2f}s - may still have blocking issues")

    return total_time < 5


if __name__ == "__main__":
    success = asyncio.run(test_concurrent_writes())
    exit(0 if success else 1)
