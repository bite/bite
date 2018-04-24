from . import Service


class REST(Service):
    """Support generic REST-based services."""

    def _failed_http_response(self, response):
        # catch invalid REST API resource requests
        if response.status_code in (400, 404):
            self.parse_response(response)
        super()._failed_http_response(response)
