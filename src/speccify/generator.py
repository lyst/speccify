from drf_spectacular.generators import SchemaGenerator


class SpeccifySchemaGenerator(SchemaGenerator):
    """SchemaGenerator that only includes endpoints using speccify.api_view"""

    def _get_paths_and_endpoints(self):
        self.endpoints = [
            (path, path_regex, method, callback)
            for path, path_regex, method, callback in self.endpoints
            if getattr(callback, "_speccify_api", False)
        ]
        result = super()._get_paths_and_endpoints()
        return result
