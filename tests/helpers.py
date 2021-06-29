import json
import sys
import types
from contextlib import contextmanager

from django.test import RequestFactory, override_settings
from drf_spectacular.views import SpectacularAPIView

from speccify.generator import SpeccifySchemaGenerator


def get_schema(urlpatterns):
    rf = RequestFactory()

    urlconf = types.ModuleType("urlconf")
    urlconf.urlpatterns = urlpatterns

    schema_view = SpectacularAPIView.as_view(
        urlconf=urlpatterns, generator_class=SpeccifySchemaGenerator
    )
    schema_request = rf.get("schema")
    schema_response = schema_view(request=schema_request, format="json")

    schema_response.render()
    schema = json.loads(schema_response.content.decode())
    return schema


@contextmanager
def root_urlconf(urlpatterns):
    urls_module = types.ModuleType("test_urls_module")
    urls_module.urlpatterns = urlpatterns

    sys.modules["test_urls_module"] = urls_module

    with override_settings(ROOT_URLCONF="test_urls_module"):
        yield
