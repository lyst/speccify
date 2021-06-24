from django.urls import path
from rest_framework.decorators import api_view as drf_api_view
from rest_framework.request import Request

from speccify.decorator import api_view
from tests.helpers import get_schema


def test_basic(rf):
    @api_view(
        methods=["GET"],
        permissions=[],
    )
    def speccify_view(request: Request) -> None:
        pass  # pragma: no cover

    @drf_api_view(["GET"])
    def drf_view(request: Request) -> None:
        pass  # pragma: no cover

    urlpatterns = [
        path("speccify_view", speccify_view),
        path("drf_view", drf_view),
    ]

    schema = get_schema(urlpatterns)
    paths = schema["paths"]
    assert "/speccify_view" in paths
    assert "/drf_view" not in paths
