from .. import Cli


class Redmine(Cli):
    """CLI for Redmine service."""

    def _render_search(self, *args, fields=None, **kw):
        """Render search data for output."""
        fields = ('id', 'title')
        output = '{:<8} {:<20}'
        yield from super()._render_search(*args, fields=fields, output=output, **kw)
