class BiteError(Exception):
    """Generic bite exceptions."""

    def __init__(self, msg, code=None, text=None):
        self.msg = str(msg)
        self.code = code
        self.text = text

    def __str__(self):
        return self.msg

    @property
    def message(self):
        if not self.text:
            return self.msg
        return ' '.join((self.msg, self.text))

class RequestError(BiteError):
    """Generic http(s) request exceptions."""

    @property
    def message(self):
        if not self.text:
            return self.msg

        # use beautifulsoup if it exists to render server response
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.text, "lxml")
            text = soup.get_text().strip()
        except ImportError:
            text = self.text
        return self.msg + ' -- (see server response below)\n\n' + text

class AuthError(RequestError):
    """Exception related to failed authentication or lack of sufficient privileges."""

    def __init__(self, msg, code=None, expired=False):
        super().__init__(msg, code)
        self.expired = expired

class BadAuthToken(RequestError):
    """Exception for old or bad authentication tokens."""
    pass

class CliError(BiteError):
    """Exception used to display graceful failures to users."""
    pass

class NotFound(RequestError):
    pass
