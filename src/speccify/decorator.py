import inspect
import functools
from dataclasses import asdict, dataclass
from typing import Any, List

from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

serializer_registry = {}


class QueryParams:
    pass


class RequestData:
    pass


@dataclass
class Empty:
    pass


class CustomDataclassSerializer(DataclassSerializer):
    def build_dataclass_field(self, field_name: str, type_info):
        """
        Create fields for dataclasses.
        """
        base_type = type_info.base_type
        if base_type not in serializer_registry:
            serializer_registry[base_type] = type(
                f"{base_type.__name__}Serializer", (DataclassSerializer,), {}
            )

        field_class = serializer_registry[base_type]
        field_kwargs = {"dataclass": base_type, "many": type_info.is_many}
        return field_class, field_kwargs


def _make_serializer(data_class):
    class Meta:
        dataclass = data_class

    serializer_name = f"{data_class.__name__}Serializer"
    serializer_cls = type(serializer_name, (CustomDataclassSerializer,), {"Meta": Meta})
    return serializer_cls


def foo_api(
    *,
    methods,
    permissions,
    default_response_code=status.HTTP_200_OK,
):
    def decorator_wrapper(view_func):
        injected_params = {}
        seen_types = set()

        signature = inspect.signature(view_func)
        for param in signature.parameters.values():
            annotation = param.annotation
            for injection_type in (QueryParams, RequestData):
                if isinstance(annotation, type) and issubclass(annotation, injection_type):
                    if injection_type in seen_types:
                        raise TypeError(
                            f"At most one `{injection_type.__name__}` parameter is allowed"
                        )
                    injected_params[param.name] = _make_serializer(annotation)
                    seen_types.add(injection_type)

        response_cls = signature.return_annotation
        if response_cls is signature.empty:
            raise TypeError("Response type annotation is required")
        if response_cls is None:
            response_cls = Empty

        response_serializer_cls = _make_serializer(response_cls)

        swagger_auto_schema_kwargs = {}
        for key, serializer_cls in injected_params.items():
            if issubclass(serializer_cls.Meta.dataclass, QueryParams):
                swagger_auto_schema_kwargs["query_serializer"] = serializer_cls
            if issubclass(serializer_cls.Meta.dataclass, RequestData):
                swagger_auto_schema_kwargs["request_body"] = serializer_cls

        @functools.wraps(view_func)
        @swagger_auto_schema(
            methods=methods,
            responses={default_response_code: response_serializer_cls},
            **swagger_auto_schema_kwargs,
        )
        @api_view(methods)
        @permission_classes(permissions)
        def wrapper(request, **kwargs):
            view_kwargs = {}
            for key, serializer_cls in injected_params.items():
                if issubclass(serializer_cls.Meta.dataclass, QueryParams):
                    serializer = serializer_cls(data=request.query_params)
                if issubclass(serializer_cls.Meta.dataclass, RequestData):
                    serializer = serializer_cls(data=request.data)

                serializer.is_valid(raise_exception=True)
                data_instance = serializer.validated_data
                view_kwargs[key] = data_instance

            response_data = view_func(request, **view_kwargs)

            if response_cls is Empty:
                assert (
                    response_data is None
                ), "Type signature says response is None, but view returned data"
                response_data = Empty()

            response_serializer = response_serializer_cls(data=asdict(response_data))
            response_serializer.is_valid(raise_exception=True)

            return Response(status=200, data=asdict(response_serializer.validated_data))

        return wrapper

    return decorator_wrapper


@dataclass
class Dispatch:
    methods: List[str]
    permissions: List[Any]
    view: Any


def foo_api_dispatch(entries):
    # TODO:
    # this approach means the view doesn't get included in the generated openapi schema
    # i _think_ that's because the function that we decorate with @swagger_auto_schema is
    # _different from the view that we mount at the url (with `path('..'. view)`)
    # see sketch of new approach in dispatch_v2 below
    method_map = {}
    for entry in entries:
        decorator = foo_api(methods=entry.methods, permissions=entry.permissions)
        decorated = decorator(entry.view)
        for method in entry.methods:
            assert method not in method_map, "Can't have overlapping entries"
            method_map[method] = decorated

    def dispatch_view(request, *a, **k):
        assert request.method in method_map, "api_view.methods should ensure this"

        view = method_map[request.method]
        return view(request, *a, **k)

    return dispatch_view


# def foo_api_dispatch_v2(entries):

#     def dispatch_view(request, *a, **k):
#         ...

#     for entry in entries:
#         @swagger_auto_schema(data)(dispatch_view)

#     return dispatch_view


# def foo_api_v2(*args):
#     def wrapper(view):
#         return foo_api_dispatch_v2([Dispatch(*args, view=view)]
#     )
