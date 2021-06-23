from dataclasses import dataclass

from rest_framework import status
from rest_framework.request import Request

from speccify.decorator import foo_api


@dataclass
class Person:
    name: str


@dataclass
class Display:
    length: str


def test_basic(rf):
    @foo_api(
        data_class=Person,
        methods=["GET"],
        responses={status.HTTP_200_OK: Display},
        permissions=[],
    )
    def view(request: Request, person: Person) -> Display:
        length = len(person.name)
        return Display(length=str(length))

    request = rf.get("/?name=value")
    response = view(request)
    assert response.data == {"length": "5"}
