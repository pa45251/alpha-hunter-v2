"""Compatibility entrypoint for portfolio-maintenance decision refresh.

The implementation moved to decision_run_with_maintenance_v2 so every publication path shares
snapshot revalidation, market-session idempotence, the V2 BROKEN guard and future-data-safe shadow
validation. This filename is kept because existing workflow references may still call it.
"""
from decision_run_with_maintenance_v2 import main


if __name__ == "__main__":
    main()
