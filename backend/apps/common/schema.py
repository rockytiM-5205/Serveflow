from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

SLUG_PARAM = OpenApiParameter(
    name="slug", type=str, location=OpenApiParameter.PATH, description="Restaurant slug"
)


def staff_schema(extra_parameters=None, **summaries):
    """Document the slug path parameter and a summary for each HTTP method, e.g.
    @staff_schema(get="List things", post="Create a thing")."""
    parameters = [SLUG_PARAM, *(extra_parameters or [])]
    return extend_schema_view(
        **{
            method: extend_schema(parameters=parameters if method == "get" else [SLUG_PARAM], summary=text)
            for method, text in summaries.items()
        }
    )
