from typing import Callable, TypeVar, cast

from rest_framework.response import Response
from typing_extensions import Protocol

F_view = TypeVar("F_view", bound=Callable[..., object])
F_add = TypeVar("F_add", bound=Callable[..., object])
T = TypeVar("T")


class ApiView(Protocol[F_view, F_add]):
    add: F_add
    _speccify_api: bool
    __call__: F_view


def attach_add(func: F_view, add: F_add) -> ApiView[F_view, F_add]:
    api_view = cast(ApiView[F_view, F_add], func)
    api_view.add = add
    return api_view


DecoratorFactory = Callable[..., Callable[..., T]]
View = Callable[..., Response]
