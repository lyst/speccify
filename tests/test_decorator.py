import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import pytest
from django.test import Client
from django.urls import path
from rest_framework import permissions
from rest_framework.decorators import permission_classes
from rest_framework.request import Request
from typing_extensions import Annotated

from speccify.decorator import Data, Query, api_view
from speccify.exceptions import CollectionError, InvalidReturnValue, OverlappingMethods
from tests.helpers import get_schema, root_urlconf


@dataclass
class Person:
    name: str


@dataclass
class Display:
    length: str


def test_basic(rf):
    @api_view(methods=["GET"])
    def view(request: Request, person: Query[Person]) -> Display:
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

    @api_view(methods=["POST"])
    def view(request: Request, person: Data[Parent]) -> None:
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
class MyData:
    d: str


@dataclass
class MyResponse:
    r: str


def test_query_params(rf):
    @api_view(methods=["GET"])
    def view(request: Request, my_query: Query[MyQueryData]) -> MyResponse:
        foo = my_query.q
        bar = len(foo)
        return MyResponse(r=str(bar))

    request = rf.get("/?q=value")
    response = view(request)
    assert response.data == {"r": "5"}


def test_extra_query_params(rf):
    @api_view(methods=["GET"])
    def view(request: Request, my_query: Query[MyQueryData]) -> None:
        assert not hasattr(my_query, "r")
        return

    request = rf.get("/?q=value&r=foo")
    response = view(request)
    assert response.status_code == 200


def test_default_query_params(rf):
    @dataclass
    class MyDefaultQueryData:
        q: Optional[str] = "foo"

    @api_view(methods=["GET"])
    def view(request: Request, my_query: Query[MyDefaultQueryData]) -> None:
        return

    request = rf.get("/")
    response = view(request)
    assert response.status_code == 200


def test_default_response_key(rf):
    @dataclass
    class MyDefaultResponse:
        r: Optional[str] = None

    @api_view(methods=["GET"])
    def view(request: Request) -> MyDefaultResponse:
        return MyDefaultResponse()

    request = rf.get("/")
    response = view(request)
    assert response.data == {"r": None}


def test_raise_type_error_if_optional_not_provided():
    @dataclass
    class OptionalWithoutDefault:
        q: Optional[str]

    def view(request: Request, my_query: Query[OptionalWithoutDefault]) -> None:
        pass  # pragma: no cover

    with pytest.raises(CollectionError) as exc_info:
        api_view(methods=["GET"])(view)

    assert "Optional fields must provide a default" in str(exc_info.value)
    assert "OptionalWithoutDefault'>.q`." in str(exc_info.value)


def test_post_data(rf):
    @api_view(methods=["POST"])
    def view(request: Request, my_data: Data[MyData]) -> MyResponse:
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

    @api_view(methods=["PUT"])
    def view(request: Request, my_query: Data[MyData]) -> None:
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

    with pytest.raises(CollectionError) as exc_info:

        @api_view(methods=["GET"])
        def view(request: Request, d1: Query[D1], d2: Query[D2]) -> None:
            pass  # pragma: no cover

    assert "At most one " in str(exc_info.value)


def test_stacking(rf):
    @dataclass
    class MyQueryData:
        q: str

    @dataclass
    class MyData:
        d: str

    @dataclass
    class MyResponse:
        r: str

    @api_view(methods=["GET"])
    def view_single(request: Request, my_data: Query[MyQueryData]) -> MyResponse:
        pass  # pragma: no cover

    @api_view(methods=["GET"])
    def view_get(request: Request, my_data: Query[MyQueryData]) -> MyResponse:
        return MyResponse(r="get")

    @view_get.add(methods=["POST"])
    def view_post(request: Request, my_data: Data[MyData]) -> MyResponse:
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

    @api_view(methods=["POST"])
    def view(request: Request, my_query: Data[Parent]) -> None:
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

    @api_view(methods=["GET"])
    def view(request: Annotated[Request, ""], my_query: Query[Data]) -> None:
        pass

    request = rf.get("/?q=value")
    response = view(request)
    assert response.status_code == 200


def test_missing_return_annotation(rf):
    with pytest.raises(CollectionError) as exc_info:

        @api_view(methods=["GET"])
        def view(request: Request):
            pass  # pragma: no cover

    assert "Response type annotation is required" in str(exc_info.value)


def test_url_path_params(client):
    @api_view(methods=["GET"])
    def view(request: Request, param: str) -> None:
        pass

    urlpatterns = [
        path("<slug:param>/", view, name="view"),
    ]

    with root_urlconf(urlpatterns):
        response = client.get("/value/")
    assert response.status_code == 200


@dataclass
class Return:
    field: str


@dataclass
class Other:
    other_field: int


@pytest.mark.parametrize(
    "return_annotation, return_value, expected",
    [
        (Return, None, "response must be a dataclass"),
        (Return, Other(other_field=0), "Invalid data returned from view"),
        (None, Return(field="value"), "view returned data"),
    ],
)
def test_invalid_return_value(rf, return_annotation, return_value, expected):
    @api_view(methods=["GET"])
    def view(request: Request) -> return_annotation:
        return return_value

    request = rf.get("/?name=value")
    with pytest.raises(InvalidReturnValue) as exc_info:
        view(request)
    assert expected in str(exc_info.value)

    urlpatterns = [
        path("view/", view),
    ]

    client = Client(raise_request_exception=False)

    with root_urlconf(urlpatterns):
        response = client.get("/view/")
        assert response.status_code == 500


def test_duplicate_methods():
    with pytest.raises(OverlappingMethods):

        @api_view(methods=["GET", "GET"])
        def view2(request: Request) -> None:
            pass  # pragma: no cover


def test_stacking_overlapping_methods():
    @api_view(methods=["GET"])
    def view1(request: Request) -> None:
        pass  # pragma: no cover

    with pytest.raises(OverlappingMethods):

        @view1.add(methods=["GET"])
        def view2(request: Request) -> None:
            pass  # pragma: no cover


def test_non_dataclass_param():
    with pytest.raises(CollectionError) as exc_info:

        @api_view(methods=["GET"])
        def view(request: Request, string: Data[str]) -> None:
            pass  # pragma: no cover

    assert str(exc_info.value) == "`<class 'str'>` must be a dataclass"


def test_name_already_used():
    @dataclass
    class Dupe:
        field: str

    copy1 = Dupe

    @dataclass
    class Dupe:
        field: str

    # different from copy1, but same class name
    copy2 = Dupe

    with pytest.raises(CollectionError) as exc_info:

        @api_view(methods=["GET"])
        def view(request: Request, c1: Data[copy1]) -> copy2:
            pass  # pragma: no cover

    assert "Name already in use" in str(exc_info.value)


def test_permissions_decorator_on_absorbed_view():
    @api_view(methods=["GET"])
    def main_view(request: Request) -> None:
        pass  # pragma: no cover

    with pytest.raises(CollectionError) as exc_info:

        @main_view.add(methods=["POST"])
        @permission_classes([])
        def added_view(request: Request) -> None:
            pass  # pragma: no cover

    assert "`@permission_classes` are shared with the parent view" in str(
        exc_info.value
    )


def test_permissions_decorator_on_main_view(client):
    class TestPermission(permissions.BasePermission):
        def has_permission(self, request, view):
            return False

    @api_view(methods=["GET"])
    @permission_classes([TestPermission])
    def main_view(request: Request) -> None:
        pass  # pragma: no cover

    @main_view.add(methods=["POST"])
    def added_view(request: Request) -> None:
        pass  # pragma: no cover

    urlpatterns = [
        path("view/", main_view),
    ]

    with root_urlconf(urlpatterns):
        response_get = client.get("/view/")
        response_post = client.post("/view/")
    assert response_get.status_code == 403
    assert response_post.status_code == 403
