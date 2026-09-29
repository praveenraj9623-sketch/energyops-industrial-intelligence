"""Local-only Apache Superset configuration. Secrets arrive through Docker env."""

import os
from urllib.parse import quote_plus

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://superset_meta:"
    + quote_plus(os.environ["SUPERSET_METADATA_PASSWORD"])
    + "@superset-metadata:5432/superset"
)
WTF_CSRF_ENABLED = True
ENABLE_PROXY_FIX = False
FEATURE_FLAGS = {"DASHBOARD_NATIVE_FILTERS": True}
ROW_LIMIT = 10000
