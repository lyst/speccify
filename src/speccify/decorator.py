import functools
from dataclasses import asdict, fields

from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response


def foo_api(*, data_class, methods, responses, permissions):
    field_map = {str: serializers.CharField}
    serializer_fields = {
        field.name: field_map[field.type]() for field in fields(data_class)
    }
    serializer_cls = type("foo", (serializers.Serializer,), serializer_fields)

    response_cls = responses.get(status.HTTP_200_OK)
    response_serializer_fields = {
        field.name: field_map[field.type]() for field in fields(response_cls)
    }
    response_serializer_cls = type(
        "foo", (serializers.Serializer,), response_serializer_fields
    )

    def decorator_wrapper(view_func):
        @functools.wraps(view_func)
        @swagger_auto_schema(
            query_serializer=serializer_cls,
            methods=methods,
            responses={status.HTTP_200_OK: response_serializer_cls},
        )
        @api_view(methods)
        @permission_classes(permissions)
        def wrapper(request, **kwargs):
            data = request.query_params
            serializer = serializer_cls(data=data)
            serializer.is_valid(raise_exception=True)

            data_instance = data_class(**serializer.validated_data)

            response_data = view_func(request, data_instance)

            response_serializer = response_serializer_cls(data=asdict(response_data))
            response_serializer.is_valid(raise_exception=True)

            return Response(status=200, data=response_serializer.validated_data)

        return wrapper

    return decorator_wrapper
