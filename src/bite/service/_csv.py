import csv
import io

from ._reqs import URLRequest
from ..exceptions import RequestError


class CSVRequest(URLRequest):
    """Construct a CSV request."""

    def parse_response(self, response):
        """Parse the raw CSV content."""
        if not response.headers.get('Content-Type', '').startswith('text/csv'):
            msg = 'non-CSV response from server'
            if not self.service.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(
                msg, code=response.status_code, text=response.text, response=response)

        # Requesting the text content of the response doesn't remove the BOM so
        # we request the binary content and decode it ourselves to remove it.
        f = io.StringIO(response.content.decode('utf-8-sig'))
        headers = [x.strip('"\'').lower() for x in f.readline().strip().split(',')]
        return csv.DictReader(f, fieldnames=headers)
