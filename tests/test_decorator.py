import json
import types
from dataclasses import dataclass
from urllib.parse import urlencode

import pytest
from django.test.client import RequestFactory
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


def _get_schema(urlpatterns):
    rf = RequestFactory()

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
    return schema


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
    schema = _get_schema(urlpatterns)
    paths = schema["paths"]
    assert "/view" in paths
    assert "get" in paths["/view"]

    assert "Child1" in schema["definitions"]


@dataclass
class MyQueryData(QueryParams):
    q: str


@dataclass
class MyRequestData(RequestData):
    d: str


@dataclass
class MyResponse:
    r: str


def test_query_params(rf):
    @foo_api(methods=["GET"], permissions=[])
    def view(request: Request, my_query: MyQueryData) -> MyResponse:
        foo = my_query.q
        bar = len(foo)
        return MyResponse(r=bar)

    request = rf.get("/?q=value")
    response = view(request)
    assert response.data == {"r": "5"}


def test_post_data(rf):
    @foo_api(
        methods=["POST"],
        permissions=[],
    )
    def view(request: Request, my_data: MyRequestData) -> MyResponse:
        foo = my_data.d
        bar = len(foo)
        return MyResponse(r=bar)

    request = rf.post("/", {"d": "value"})
    response = view(request)
    assert response.data == {"r": "5"}


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


def test_stacking(rf):
    @dataclass
    class MyQueryData(QueryParams):
        q: str

    @dataclass
    class MyRequestData(RequestData):
        d: str

    @dataclass
    class MyResponse:
        r: str

    @foo_api(methods=["GET"], permissions=[])
    def view_single(request: Request, my_data: MyQueryData) -> MyResponse:
        pass

    @foo_api(methods=["GET"], permissions=[])
    def view_get(request: Request, my_data: MyQueryData) -> MyResponse:
        return MyResponse(r="get")

    @view_get.dispatch(methods=["POST"], permissions=[])
    def view_post(request: Request, my_data: MyRequestData) -> MyResponse:
        return MyResponse(r="post")

    get_request = rf.get("/?q=value")
    get_response = view_get(get_request)
    get_response.render()
    assert get_response.data == {"r": "get"}

    post_request = rf.post("/", data={"d": "value"})
    post_response = view_get(post_request)
    assert post_response.data == {"r": "post"}

    with pytest.raises(TypeError):
        # should not be possible to mount this one
        path("bad", view_post)

    urlpatterns = [
        path("single", view_single),
        path("multiple", view_get),
    ]
    schema = _get_schema(urlpatterns)

    paths = schema["paths"]
    assert "/single" in paths
    assert "get" in paths["/single"]

    assert "/multiple" in paths
    assert "get" in paths["/multiple"]
    assert "post" in paths["/multiple"]
