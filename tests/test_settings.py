INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
]

SECRET_KEY = "secret"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
