import json
import types
from dataclasses import dataclass

from django.urls import path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import status
from rest_framework.request import Request

from speccify.decorator import foo_api


@dataclass
class Person:
    name: str


@dataclass
class Display:
    length: str


def test_basic(rf):
    @foo_api(
        data_class=Person,
        methods=["GET"],
        responses={status.HTTP_200_OK: Display},
        permissions=[],
    )
    def view(request: Request, person: Person) -> Display:
        length = len(person.name)
        return Display(length=str(length))

    request = rf.get("/?name=value")
    response = view(request)
    assert response.data == {"length": "5"}


def test_schema(rf):
    @dataclass
    class Child1:
        pass

    @dataclass
    class Child2:
        pass

    @dataclass
    class Parent:
        child1: Child1
        child2: Child2

    @foo_api(
        data_class=Person,
        methods=["GET"],
        responses={status.HTTP_200_OK: Parent},
        permissions=[],
    )
    def view(request: Request, person: Person) -> Parent:
        pass

    urlpatterns = [
        path("view", view),
    ]
    urlconf = types.ModuleType("urlconf")
    urlconf.urlpatterns = urlpatterns

    schema_view = get_schema_view(
        openapi.Info(
            title="",
            default_version="v1",
        ),
        public=True,
        urlconf=urlconf,
    )

    schema_request = rf.get("schema")
    schema_response = schema_view.without_ui(cache_timeout=0)(
        request=schema_request, format=".json"
    )

    schema_response.render()
    schema = json.loads(schema_response.content.decode())
    paths = schema["paths"]
    assert "/view" in paths
    assert "get" in paths["/view"]

    assert "Child1" in schema["definitions"]
