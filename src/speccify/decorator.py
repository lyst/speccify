import dataclasses
import functools
import re
from dataclasses import dataclass
from typing import Any, Dict, Tuple, TypeVar, Union

import typing_extensions
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view as drf_api_view
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer
from typing_extensions import Annotated

serializer_registry = {}
registered_class_names = {}

NoneType = type(None)
_T = TypeVar("_T")


class _Marker:
    """Used for marker error messages"""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return f"<{self.name}>"


_query_params = _Marker("Query")
_request_data = _Marker("Data")

Query = Annotated[_T, _query_params]
Data = Annotated[_T, _request_data]


@dataclass
class Empty:
    pass


class AbsorbedView:
    """This view has been absorbed into another using `view.add`

    The absorbed view should not be attached to an url, or ever called. To call it, call the
    parent view using a request with a matching method for this view.
    """

    def __init__(self, parent_view_name):
        self.parent_view_name = parent_view_name

    def __repr__(self):
        return f"<AbsorbedView (parent={self.parent_view_name})>"


class CustomDataclassSerializer(DataclassSerializer):
    def build_dataclass_field(self, field_name: str, type_info):
        """
        Create fields for dataclasses.
        """
        base_type = type_info.base_type
        field_class = _make_serializer(base_type)
        field_kwargs = {"many": type_info.is_many}
        return field_class, field_kwargs


def _is_optional(field_type):
    # https://stackoverflow.com/questions/56832881/check-if-a-field-is-typing-optional
    return typing_extensions.get_origin(field_type) is Union and type(
        None
    ) in typing_extensions.get_args(field_type)


def _make_serializer(data_class):
    if data_class not in serializer_registry:
        name_used_by = registered_class_names.get(data_class.__name__)
        if name_used_by:
            raise TypeError(
                f"Error collecting `{data_class}`. Name already in use by `{name_used_by}`"
            )
        try:
            fields = dataclasses.fields(data_class)
        except TypeError as exc:
            raise TypeError(f"`{data_class}` must be a dataclass") from exc

        for field in fields:
            if _is_optional(field.type) and (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            ):
                raise TypeError(
                    f"Error collecting `{data_class}.{field.name}`. Optional fields must provide a default"
                )

        class Meta:
            dataclass = data_class

        serializer_name = f"{data_class.__name__}Serializer"
        serializer_registry[data_class] = type(
            serializer_name,
            (CustomDataclassSerializer,),
            {"Meta": Meta, "__doc__": data_class.__doc__},
        )
        registered_class_names[data_class.__name__] = data_class

    return serializer_registry[data_class]


def add_methods(view_func, methods):
    # small hack to attach more http methods to a view already decorated with drf.api_view

    # assumes something else has checked that these methods are not already set
    # we check before calling `add_methods`
    existing_methods = view_func.cls.http_method_names

    # we just need access to the handler, which is the same for all methods except `options` (which
    # is added by drf with a custom handler)
    existing_method = next(method for method in existing_methods if method != "options")
    handler = getattr(view_func.cls, existing_method)
    methods = [method.lower() for method in methods]
    for method in methods:
        setattr(view_func.cls, method, handler)
    view_func.cls.http_method_names.extend(methods)


@dataclass
class ViewDescriptor:
    view_func: Any  # callable?
    injected_params: Dict[str, Tuple[_Marker, DataclassSerializer]]
    response_serializer_cls: DataclassSerializer

    @classmethod
    def from_view(cls, view_func):
        injected_params = {}
        seen_types = set()

        parameters = typing_extensions.get_type_hints(view_func, include_extras=True)

        for name, annotation in parameters.items():
            if name == "return":
                continue

            if not typing_extensions.get_origin(annotation) is Annotated:
                continue
            data_class, marker, *_ = typing_extensions.get_args(annotation)
            if not isinstance(marker, _Marker):
                continue

            if marker in seen_types:
                raise TypeError(f"At most one `{marker}` parameter is allowed")
            serializer = _make_serializer(data_class)
            injected_params[name] = (marker, serializer)
            seen_types.add(marker)

        if "return" not in parameters:
            raise TypeError("Response type annotation is required")
        response_cls = parameters["return"]
        if response_cls is NoneType:
            response_cls = Empty

        response_serializer_cls = _make_serializer(response_cls)

        return cls(
            view_func=view_func,
            injected_params=injected_params,
            response_serializer_cls=response_serializer_cls,
        )

    def docs(self):
        """Parse docstring into title/summary"""

        # split off using the first blank line
        parts = re.split(r"\n\s*\n", self.view_func.__doc__ or "", 1)
        if len(parts) == 1:
            parts.append("")
        title, summary = parts
        return title, summary

    def extend_schema_kwargs(self, methods, default_response_code):
        kwargs = {}
        for key, (marker, serializer_cls) in self.injected_params.items():
            if marker is _query_params:
                kwargs["parameters"] = [serializer_cls]
            if marker is _request_data:
                kwargs["request"] = serializer_cls

        kwargs["methods"] = methods
        kwargs["responses"] = {default_response_code: self.response_serializer_cls}

        title, summary = self.docs()
        kwargs["summary"] = title
        kwargs["description"] = summary
        return kwargs


def api_view(
    *,
    methods,
    permissions,
    default_response_code=status.HTTP_200_OK,
):
    """Decorator to annotate views. Calls drf's api_view and drf-spectacular's extend_schema

    Usage:

    >>>  @dataclass
    >>>  class MyQueryData():
    >>>      name: str

    >>>  @dataclass
    >>>  class MyResponse:
    >>>      length: int

    >>>  @api_view(methods=["GET"], permissions=[])
    >>>  def my_view(request: Request, my_query: Query[MyQueryData]) -> MyResponse:
    >>>      name = my_query.name
    >>>      length = len(name)
    >>>      return MyResponse(length=length)

    To use different views for the same url (with different http methods), define the first one as above, and then add subsequent ones using `my_view.add`

    >>>  @my_view.add(methods=["POST"])
    >>>  def my_other_view(...)
    >>>      ...

    `.add()` doesn't accept the `permissions`, since they must be shared with the original view
    """

    def decorator_wrapper(view_func):
        main_view_name = view_func.__name__
        view_descriptor = ViewDescriptor.from_view(view_func)

        method_map = {}
        for method in methods:
            assert method not in method_map, "overlapping methods are not allowed"
            method_map[method] = view_descriptor

        @functools.wraps(view_func)
        @extend_schema(
            **view_descriptor.extend_schema_kwargs(methods, default_response_code)
        )
        @drf_api_view(methods)
        @permission_classes(permissions)
        def wrapper(request, **kwargs):
            assert (
                request.method in method_map
            ), "drf_api_view.methods should ensure this"
            view_descriptor = method_map[request.method]
            view_kwargs = kwargs
            for key, (
                marker,
                serializer_cls,
            ) in view_descriptor.injected_params.items():
                if marker is _query_params:
                    serializer = serializer_cls(data=request.query_params)
                if marker is _request_data:
                    serializer = serializer_cls(data=request.data)

                serializer.is_valid(raise_exception=True)
                data_instance = serializer.validated_data
                view_kwargs[key] = data_instance

            response_data = view_descriptor.view_func(request, **view_kwargs)

            if view_descriptor.response_serializer_cls.Meta.dataclass is Empty:
                assert (
                    response_data is None
                ), "Type signature says response is None, but view returned data"
                response_data = Empty()

            response_serializer = view_descriptor.response_serializer_cls(
                data=dataclasses.asdict(response_data)
            )
            response_serializer.is_valid(raise_exception=True)

            return Response(
                status=200, data=dataclasses.asdict(response_serializer.validated_data)
            )

        def add(
            *,
            methods,
            default_response_code=status.HTTP_200_OK,
        ):
            def decorator_wrapper(view_func):
                view_descriptor = ViewDescriptor.from_view(view_func)
                for method in methods:
                    assert (
                        method not in method_map
                    ), "overlapping methods are not allowed"
                    method_map[method] = view_descriptor
                add_methods(wrapper, methods)
                extend_schema_decorator = extend_schema(
                    **view_descriptor.extend_schema_kwargs(
                        methods, default_response_code
                    )
                )
                extend_schema_decorator(wrapper)

                # this view should not be attached to an url, or ever called. to call it, call the
                # "parent" view using a request with a matching method for this view
                return AbsorbedView(main_view_name)

            return decorator_wrapper

        wrapper.add = add
        wrapper._speccify_api = True
        return wrapper

    return decorator_wrapper
