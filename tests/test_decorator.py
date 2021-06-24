import json
import sys
import types
from dataclasses import dataclass
from typing import Annotated, Optional
from urllib.parse import urlencode

import pytest
from django.urls import path
from rest_framework.request import Request

from speccify.decorator import (
    QueryParams,
    RequestData,
    api_view,
    registered_class_names,
    serializer_registry,
)
from tests.helpers import get_schema


@pytest.fixture(autouse=True)
def reset_serializer_registry():
    registry_before = serializer_registry.copy()
    names_before = registered_class_names.copy()
    yield
    serializer_registry.clear()
    serializer_registry.update(registry_before)
    registered_class_names.clear()
    registered_class_names.update(names_before)


@dataclass
class Person:
    name: str


@dataclass
class Display:
    length: str


def test_basic(rf):
    @api_view(
        methods=["GET"],
        permissions=[],
    )
    def view(request: Request, person: QueryParams[Person]) -> Display:
        length = len(person.name)
        return Display(length=str(length))

    request = rf.get("/?name=value")
    response = view(request)
    assert response.data == {"length": "5"}


def test_schema(rf):
    @dataclass
    class Child1:
        c1: str

    @dataclass
    class Child2:
        c1: str

    @dataclass
    class Parent:
        child1: Child1
        child2: Child2

    @api_view(
        methods=["POST"],
        permissions=[],
    )
    def view(request: Request, person: RequestData[Parent]) -> None:
        pass  # pragma: no cover

    urlpatterns = [
        path("view", view),
    ]
    schema = get_schema(urlpatterns)
    paths = schema["paths"]
    assert "/view" in paths
    assert "post" in paths["/view"]

    assert "Child1" in schema["components"]["schemas"]


@dataclass
class MyQueryData:
    q: str


@dataclass
class MyRequestData:
    d: str


@dataclass
class MyResponse:
    r: str


def test_query_params(rf):
    @api_view(methods=["GET"], permissions=[])
    def view(request: Request, my_query: QueryParams[MyQueryData]) -> MyResponse:
        foo = my_query.q
        bar = len(foo)
        return MyResponse(r=str(bar))

    request = rf.get("/?q=value")
    response = view(request)
    assert response.data == {"r": "5"}


def test_extra_query_params(rf):
    @api_view(methods=["GET"], permissions=[])
    def view(request: Request, my_query: QueryParams[MyQueryData]) -> None:
        assert not hasattr(my_query, "r")
        return

    request = rf.get("/?q=value&r=foo")
    response = view(request)
    assert response.status_code == 200


def test_default_query_params(rf):
    @dataclass
    class MyDefaultQueryData:
        q: Optional[str] = "foo"

    @api_view(methods=["GET"], permissions=[])
    def view(request: Request, my_query: QueryParams[MyDefaultQueryData]) -> None:
        return

    request = rf.get("/")
    response = view(request)
    assert response.status_code == 200


def test_default_response_key(rf):
    @dataclass
    class MyDefaultResponse:
        r: Optional[str] = None

    @api_view(methods=["GET"], permissions=[])
    def view(request: Request) -> MyDefaultResponse:
        return MyDefaultResponse()

    request = rf.get("/")
    response = view(request)
    assert response.data == {"r": None}


def test_raise_type_error_if_optional_not_provided():
    @dataclass
    class OptionalWithoutDefault:
        q: Optional[str]

    def view(request: Request, my_query: QueryParams[OptionalWithoutDefault]) -> None:
        pass  # pragma: no cover

    with pytest.raises(TypeError) as exc_info:
        api_view(methods=["GET"], permissions=[])(view)

    assert "Optional fields must provide a default" in str(exc_info.value)
    assert "OptionalWithoutDefault'>.q`." in str(exc_info.value)


def test_post_data(rf):
    @api_view(
        methods=["POST"],
        permissions=[],
    )
    def view(request: Request, my_data: RequestData[MyRequestData]) -> MyResponse:
        foo = my_data.d
        bar = len(foo)
        return MyResponse(r=str(bar))

    request = rf.post("/", {"d": "value"})
    response = view(request)
    assert response.data == {"r": "5"}


def test_urlencoded_request_data(rf):
    @dataclass
    class MyData:
        foo: str

    @api_view(
        methods=["PUT"],
        permissions=[],
    )
    def view(request: Request, my_query: RequestData[MyData]) -> None:
        assert my_query.foo == "bar"

    request = rf.put(
        "/foo", urlencode({"foo": "bar"}), "application/x-www-form-urlencoded"
    )

    response = view(request)
    assert response.status_code == 200


def test_disallows_multiple_query_param_arguments():
    @dataclass
    class D1:
        foo: str

    class D2:
        bar: str

    with pytest.raises(TypeError) as exc_info:

        @api_view(
            methods=["GET"],
            permissions=[],
        )
        def view(request: Request, d1: QueryParams[D1], d2: QueryParams[D2]) -> None:
            pass  # pragma: no cover

    assert "At most one " in str(exc_info.value)


def test_stacking(rf):
    @dataclass
    class MyQueryData:
        q: str

    @dataclass
    class MyRequestData:
        d: str

    @dataclass
    class MyResponse:
        r: str

    @api_view(methods=["GET"], permissions=[])
    def view_single(request: Request, my_data: QueryParams[MyQueryData]) -> MyResponse:
        pass  # pragma: no cover

    @api_view(methods=["GET"], permissions=[])
    def view_get(request: Request, my_data: QueryParams[MyQueryData]) -> MyResponse:
        return MyResponse(r="get")

    @view_get.add(methods=["POST"])
    def view_post(request: Request, my_data: RequestData[MyRequestData]) -> MyResponse:
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

    assert "AbsorbedView" in repr(view_post)

    urlpatterns = [
        path("single", view_single),
        path("multiple", view_get),
    ]
    schema = get_schema(urlpatterns)

    paths = schema["paths"]
    assert "/single" in paths
    assert "get" in paths["/single"]

    assert "/multiple" in paths
    assert "get" in paths["/multiple"]
    assert "post" in paths["/multiple"]


def test_nested_serializer(rf):
    @dataclass
    class Child:
        v: str

    @dataclass
    class Parent:
        c: Child

    my_query_value = None

    @api_view(methods=["POST"], permissions=[])
    def view(request: Request, my_query: RequestData[Parent]) -> None:
        nonlocal my_query_value
        my_query_value = my_query

    request = rf.post("/", json.dumps({"c": {"v": "val"}}), "application/json")
    response = view(request)
    assert response.status_code == 200

    assert my_query_value.c.v == "val"


def test_non_marker_annotation(rf):
    @dataclass
    class Data:
        q: str

    @api_view(methods=["GET"], permissions=[])
    def view(request: Annotated[Request, ""], my_query: QueryParams[Data]) -> None:
        pass

    request = rf.get("/?q=value")
    response = view(request)
    assert response.status_code == 200


def test_missing_return_annotation(rf):
    with pytest.raises(TypeError) as exc_info:

        @api_view(methods=["GET"], permissions=[])
        def view(request: Request):
            pass  # pragma: no cover

    assert "Response type annotation is required" in str(exc_info.value)


def test_url_path_params(settings, client):
    @api_view(methods=["GET"], permissions=[])
    def view(request: Request, param: str) -> None:
        pass

    urlpatterns = [
        path("<slug:param>/", view, name="view"),
    ]

    urls_module = types.ModuleType("test_urls_module")
    urls_module.urlpatterns = urlpatterns

    sys.modules["test_urls_module"] = urls_module

    settings.ROOT_URLCONF = "test_urls_module"
    response = client.get("/value/")
    assert response.status_code == 200
