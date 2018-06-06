import csv
import io

from ._reqs import URLRequest


class CSVRequest(URLRequest):
    """Construct a CSV request."""

    def parse_response(self, response):
        """Parse the raw CSV content."""
        # Requesting the text content of the response doesn't remove the BOM so
        # we request the binary content and decode it ourselves to remove it.
        f = io.StringIO(response.content.decode('utf-8-sig'))
        headers = [x.lower() for x in f.readline().strip().split(',')]
        return csv.DictReader(f, fieldnames=headers)
