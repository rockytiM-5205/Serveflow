from django.http import JsonResponse
from django.views.defaults import page_not_found

from .exceptions import error_body


def not_found(request, exception, template_name="404.html"):
    """JSON 404 for unknown /api/ paths; Django's normal page elsewhere."""
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("not_found", "Not found."), status=404)
    return page_not_found(request, exception, template_name=template_name)
