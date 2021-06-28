from dataclasses import dataclass

from django.urls import path
from rest_framework.request import Request

from speccify import Data, Query, api_view


@dataclass
class MyInfo:
    val: str


@api_view(methods=["GET"], permissions=[])
def view_get(request: Request, query: Query[MyInfo]) -> None:
    pass


@view_get.add(methods=["POST"])
def view_post(request: Request, data: Data[MyInfo]) -> None:
    pass


path("path", view_get)
