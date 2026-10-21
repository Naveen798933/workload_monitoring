"""Application entrypoint alias for Vercel and WSGI servers."""

from index import handler, app

__all__ = ["handler", "app"]
