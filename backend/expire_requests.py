"""Optional scheduled maintenance: python backend/expire_requests.py."""

from app import get_db
from lifecycle import expire_requests

if __name__ == "__main__":
    with get_db() as db:
        count = expire_requests(db)
    print(f"Expired {count} unanswered requests.")
