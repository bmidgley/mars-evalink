from evalink.cloudflare_access import authenticate_request


class CloudflareAccessMiddleware:
    """
    Log users in from Cloudflare Access JWTs before views run.

    Place after AuthenticationMiddleware so an existing session is respected,
    but Access can still replace the session when the identity changes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        authenticate_request(request)
        return self.get_response(request)
