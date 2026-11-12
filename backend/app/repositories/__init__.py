"""Persistence adapters (Phase 5): thin async functions over SQLAlchemy sessions.

Services own transactions (they call `session.commit()`); repositories only read and
stage changes, so several repository calls can share one atomic unit of work.
"""
