#!/usr/bin/env python3
"""
Clear stuck queue items that are pending but have no active Celery task.
This is useful when workers were killed/restarted and tasks are orphaned.
"""

import sys
from pathlib import Path

# Add project root to path so we can import from database, models, etc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models.queue_item import QueueItem, QueueStatus


def clear_stuck_pending_items():
    """Delete all PENDING queue items (they've lost their Celery tasks)."""
    db = SessionLocal()
    try:
        # Find all PENDING items
        pending_items = db.query(QueueItem).filter(
            QueueItem.status == QueueStatus.PENDING
        ).all()

        if not pending_items:
            print("✓ No stuck PENDING items found")
            return

        print(f"Found {len(pending_items)} PENDING items:")
        for item in pending_items:
            print(f"  - {item.id}: {item.recipient_name} (created: {item.created_at})")

        # Ask for confirmation
        response = input(f"\nDelete all {len(pending_items)} PENDING items? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            return

        # Delete them
        for item in pending_items:
            db.delete(item)

        db.commit()
        print(f"✓ Deleted {len(pending_items)} stuck PENDING items")
        print("\nYou can now resubmit these tasks from the frontend")

    finally:
        db.close()


if __name__ == "__main__":
    clear_stuck_pending_items()
