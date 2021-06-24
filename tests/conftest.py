import pytest

from speccify.decorator import registered_class_names, serializer_registry


@pytest.fixture(autouse=True)
def reset_serializer_registry():
    registry_before = serializer_registry.copy()
    names_before = registered_class_names.copy()
    yield
    serializer_registry.clear()
    serializer_registry.update(registry_before)
    registered_class_names.clear()
    registered_class_names.update(names_before)
