import json
import types

from django.test.client import RequestFactory
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
