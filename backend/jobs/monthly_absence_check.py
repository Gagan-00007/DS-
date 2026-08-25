"""
Scheduled job that runs the monthly absence check. Wired into main.py via
APScheduler for a real deployment, but per spec section 4 (build order),
it's fine — even better for demo-day reliability — to trigger this
manually via a button/endpoint instead of trusting real scheduling to
line up with your demo slot.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import notifications


def run():
    db = SessionLocal()
    try:
        count = notifications.run_monthly_check_for_all_students(db)
        print(f"Monthly absence check complete — {count} notification(s) created.")
        return count
    finally:
        db.close()


if __name__ == "__main__":
    run()
