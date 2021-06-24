import functools
from dataclasses import asdict, dataclass

from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from typing import Any, List

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


def foo_api(
    *,
    methods,
    permissions,
    default_response_code=status.HTTP_200_OK,
):
    def decorator_wrapper(view_func):

        import inspect

        signature = inspect.signature(view_func)
        query_param_entries = {}
        request_data_entries = {}
        for param in signature.parameters.values():
            annotation = param.annotation
            if isinstance(annotation, type) and issubclass(annotation, QueryParams):
                query_param_entries[param.name] = annotation
            if isinstance(annotation, type) and issubclass(annotation, RequestData):
                request_data_entries[param.name] = annotation

        if len(query_param_entries) == 1:
            (query_data_key,) = query_param_entries.keys()
            (query_data_class,) = query_param_entries.values()

            class QueryDataMeta:
                dataclass = query_data_class

            query_serializer_name = f"{query_data_class.__name__}Serializer"
            query_serializer_cls = type(
                query_serializer_name,
                (CustomDataclassSerializer,),
                {"Meta": QueryDataMeta},
            )

        elif len(query_param_entries) == 0:
            query_data_key = None

        else:
            # len > 1
            raise TypeError("At most one `QueryParams` parameter is allowed")

        if len(request_data_entries) == 1:
            (request_data_key,) = request_data_entries.keys()
            (request_data_class,) = request_data_entries.values()

            class RequestDataMeta:
                dataclass = request_data_class

            request_serializer_name = f"{request_data_class.__name__}Serializer"
            request_serializer_cls = type(
                request_serializer_name,
                (CustomDataclassSerializer,),
                {"Meta": RequestDataMeta},
            )

        elif len(request_data_entries) == 0:
            request_data_key = None

        else:
            # len > 1
            raise TypeError("At most one `RequestData` parameter is allowed")

        response_cls = signature.return_annotation
        if response_cls is signature.empty:
            raise TypeError("Response type annotation is required")
        if response_cls is None:
            response_cls = Empty

        class ResponseMeta:
            dataclass = response_cls

        response_serializer_name = f"{response_cls.__name__}Serializer"
        response_serializer_cls = type(
            response_serializer_name,
            (CustomDataclassSerializer,),
            {"Meta": ResponseMeta},
        )

        swagger_auto_schema_kwargs = {}
        if query_data_key is not None:
            swagger_auto_schema_kwargs["query_serializer"] = query_serializer_cls
        if request_data_key is not None:
            swagger_auto_schema_kwargs["request_body"] = request_serializer_cls

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
            if query_data_key is not None:
                query_serializer = query_serializer_cls(data=request.query_params)
                query_serializer.is_valid(raise_exception=True)

                query_data_instance = query_serializer.validated_data
                view_kwargs[query_data_key] = query_data_instance

            if request_data_key is not None:
                request_serializer = request_serializer_cls(data=request.data)
                request_serializer.is_valid(raise_exception=True)

                request_data_instance = request_serializer.validated_data
                view_kwargs[request_data_key] = request_data_instance

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
