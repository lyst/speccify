import json
import types
from dataclasses import dataclass
from urllib.parse import urlencode

import pytest
from django.urls import path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.request import Request

from speccify.decorator import QueryParams, RequestData, foo_api


@dataclass
class Person(QueryParams):
    name: str


@dataclass
class Display:
    length: str


def test_basic(rf):
    @foo_api(
        methods=["GET"],
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
        methods=["GET"],
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


def test_query_params(rf):
    @dataclass
    class MyQueryData(QueryParams):
        foo: str

    @dataclass
    class MyResponse:
        bar: int

    @foo_api(
        methods=["GET"],
        permissions=[],
    )
    def view(request: Request, my_query: MyQueryData) -> MyResponse:
        foo = my_query.foo
        bar = len(foo)
        return MyResponse(bar=bar)

    request = rf.get("/?foo=value")
    response = view(request)
    assert response.data == {"bar": 5}


def test_post_data(rf):
    @dataclass
    class MyPostData(RequestData):
        foo: str

    @dataclass
    class MyResponse:
        bar: int

    @foo_api(
        methods=["POST"],
        permissions=[],
    )
    def view(request: Request, my_data: MyPostData) -> MyResponse:
        foo = my_data.foo
        bar = len(foo)
        return MyResponse(bar=bar)

    request = rf.post("/", {"foo": "value"})
    response = view(request)
    assert response.data == {"bar": 5}


def test_urlencoded_request_data(rf):
    @dataclass
    class MyData(RequestData):
        foo: str

    @foo_api(
        methods=["PUT"],
        permissions=[],
    )
    def view(request: Request, my_query: MyData) -> None:
        assert my_query.foo == "bar"

    request = rf.put(
        "/foo", urlencode({"foo": "bar"}), "application/x-www-form-urlencoded"
    )

    response = view(request)
    assert response.status_code == 200


def test_disallows_multiple_query_param_arguments():
    @dataclass
    class D1(QueryParams):
        foo: str

    class D2(QueryParams):
        bar: str

    with pytest.raises(TypeError) as exc_info:

        @foo_api(
            methods=["GET"],
            permissions=[],
        )
        def view(request: Request, d1: D1, d2: D2) -> None:
            pass

    assert "At most one " in str(exc_info.value)
