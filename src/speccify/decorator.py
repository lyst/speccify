import functools
from dataclasses import asdict

from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer


class CustomDataclassSerializer(DataclassSerializer):
    def build_dataclass_field(self, field_name: str, type_info):
        """
        Create fields for dataclasses.
        """

        field_class = type(
            f"DCS__{type_info.base_type.__name__}Serializer", (DataclassSerializer,), {}
        )
        field_kwargs = {"dataclass": type_info.base_type, "many": type_info.is_many}
        return field_class, field_kwargs


def foo_api(*, data_class, methods, responses, permissions):
    class RequestDataMeta:
        dataclass = data_class

    serializer_name = f"{data_class.__name__}Serializer"
    serializer_cls = type(
        serializer_name, (CustomDataclassSerializer,), {"Meta": RequestDataMeta}
    )

    response_cls = responses.get(status.HTTP_200_OK)

    class ResponseMeta:
        dataclass = response_cls

    serializer_name = f"{response_cls.__name__}Serializer"
    response_serializer_cls = type(
        "foo", (CustomDataclassSerializer,), {"Meta": ResponseMeta}
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

            data_instance = serializer.validated_data

            response_data = view_func(request, data_instance)

            response_serializer = response_serializer_cls(data=asdict(response_data))
            response_serializer.is_valid(raise_exception=True)

            return Response(status=200, data=asdict(response_serializer.validated_data))

        return wrapper

    return decorator_wrapper
