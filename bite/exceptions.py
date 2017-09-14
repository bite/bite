class RequestError(Exception):
    """Generic http(s) request exceptions."""

    def __init__(self, msg, code=None):
        self.msg = msg
        self.code = code

    def __str__(self):
        return self.msg

class AuthError(RequestError):
    """Exception related to failed authentication or lack of sufficient privileges."""

    def __init__(self, msg, code=None, expired=False):
        super().__init__(msg, code)
        self.expired = expired

class BadAuthToken(RequestError):
    """Exception for old or bad authentication tokens."""
    pass

class CommandError(Exception):
    pass

class CliError(Exception):
    """Exception used to display graceful failures to users."""
    pass

class NotFound(RequestError):
    pass
