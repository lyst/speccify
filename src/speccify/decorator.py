import functools
import inspect
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict

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


def _make_serializer(data_class):
    if data_class not in serializer_registry:

        class Meta:
            dataclass = data_class

        serializer_name = f"{data_class.__name__}Serializer"
        serializer_registry[data_class] = type(
            serializer_name, (CustomDataclassSerializer,), {"Meta": Meta}
        )

    return serializer_registry[data_class]


def add_more_methods(view_func, methods):
    # small hack to attach more http methods to a view already decorated with drf.api_view

    # assumes something else has checked that these methods are not already set
    existing_methods = view_func.cls.http_method_names
    # TODO: re-check for overlap?

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
    injected_params: Dict[str, DataclassSerializer]
    response_serializer_cls: DataclassSerializer

    @classmethod
    def from_view(cls, view_func):
        injected_params = {}
        seen_types = set()

        signature = inspect.signature(view_func)
        for param in signature.parameters.values():
            annotation = param.annotation
            for injection_type in (QueryParams, RequestData):
                if isinstance(annotation, type) and issubclass(
                    annotation, injection_type
                ):
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

    def swagger_auto_schema_kwargs(self, methods, default_response_code):
        kwargs = {}
        for key, serializer_cls in self.injected_params.items():
            if issubclass(serializer_cls.Meta.dataclass, QueryParams):
                kwargs["query_serializer"] = serializer_cls
            if issubclass(serializer_cls.Meta.dataclass, RequestData):
                kwargs["request_body"] = serializer_cls

        kwargs["methods"] = methods
        kwargs["responses"] = {default_response_code: self.response_serializer_cls}

        title, summary = self.docs()
        kwargs["operation_summary"] = title
        kwargs["operation_description"] = summary
        return kwargs


def foo_api(
    *,
    methods,
    permissions,
    default_response_code=status.HTTP_200_OK,
):
    def decorator_wrapper(view_func):
        main_view_name = view_func.__name__
        view_descriptor = ViewDescriptor.from_view(view_func)

        method_map = {}
        for method in methods:
            assert method not in method_map, "overlapping methods are not allowed"
            method_map[method] = view_descriptor

        @functools.wraps(view_func)
        @swagger_auto_schema(
            **view_descriptor.swagger_auto_schema_kwargs(methods, default_response_code)
        )
        @api_view(methods)
        @permission_classes(permissions)
        def wrapper(request, **kwargs):
            assert request.method in method_map, "api_view.methods should ensure this"
            view_descriptor = method_map[request.method]
            view_kwargs = {}
            for key, serializer_cls in view_descriptor.injected_params.items():
                if issubclass(serializer_cls.Meta.dataclass, QueryParams):
                    serializer = serializer_cls(data=request.query_params)
                if issubclass(serializer_cls.Meta.dataclass, RequestData):
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
                data=asdict(response_data)
            )
            response_serializer.is_valid(raise_exception=True)

            return Response(status=200, data=asdict(response_serializer.validated_data))

        # TODO: can we share this with foo_api better?
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
                add_more_methods(wrapper, methods)
                swagger_decorator = swagger_auto_schema(
                    **view_descriptor.swagger_auto_schema_kwargs(
                        methods, default_response_code
                    )
                )
                swagger_decorator(wrapper)

                # this view should not be attached to an url, or ever called. to call it, call the
                # "parent" view using a request with a matching method for this view
                return AbsorbedView(main_view_name)

            return decorator_wrapper

        # TODO: name
        # dispatch, add, add_view, mount, ..?
        wrapper.add = add
        return wrapper

    return decorator_wrapper
