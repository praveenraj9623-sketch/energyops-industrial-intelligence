-- The configured energyops_app user creates and owns these objects. Block PUBLIC schema use.
REVOKE ALL ON SCHEMA raw, staging, analytics, monitoring FROM PUBLIC;
