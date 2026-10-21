"""Server entrypoint alias for Vercel and standalone servers."""

from index import handler, app

__all__ = ["handler", "app"]
