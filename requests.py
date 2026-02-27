# Minimal requests stub for tests that only import requests but not call it.
class HTTPError(Exception):
    """Minimal HTTPError placeholder used by callers that catch requests.HTTPError."""
    pass

class DummyResponse:
    def __init__(self, status_code=503, data=None):
        self.status_code = status_code
        self._data = data or {}
    def json(self):
        return self._data


def post(*args, **kwargs):
    # Return a dummy response indicating service unavailable.
    return DummyResponse(status_code=503, data={})

__all__ = ['post', 'DummyResponse', 'HTTPError']
