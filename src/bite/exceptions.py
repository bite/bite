import lxml.html


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
        return f'{self.msg} -- {self.text}'


class RequestError(BiteError):
    """Generic http(s) request exceptions."""

    def __init__(self, *args, request=None, response=None, **kw):
        self.request = request
        self.response = response
        super().__init__(*args, **kw)

    @property
    def message(self):
        if not self.text:
            return self.msg
        doc = lxml.html.fromstring(self.text)
        text = doc.text_content().strip()
        return f"{self.msg} -- (see server response below)\n\n{text}"


class ConfigError(BiteError):
    """Failed to parse or load config file(s)."""

    def __init__(self, msg, *, path=None, **kw):
        if path:
            msg = f'failed loading {path!r}: {msg}'
        super().__init__(msg=msg, **kw)


class ParsingError(BiteError):
    """Parser failed to process the returned data."""
    pass


class AuthError(RequestError):
    """Exception related to failed authentication or lack of sufficient privileges."""

    def __init__(self, msg, code=None, expired=False, text=None):
        super().__init__(msg, code=code, text=text)
        self.expired = expired


class BadAuthToken(RequestError):
    """Exception for old or bad authentication tokens."""
    pass
