# Speccify

Tie together `drf-spectacular` and `djangorestframework-dataclasses` for
easy-to-use apis and openapi schemas.

## Usage

```
    @dataclass
    class MyQueryData():
        name: str

    @dataclass
    class MyResponse:
        length: int

    @speccify.api_view(methods=["GET"], permissions=[])
    def my_view(request: Request, my_query: QueryParams[MyQueryData]) -> MyResponse:
        name = my_query.name
        length = len(name)
        return MyResponse(length=length)
```


## License

Apache2
