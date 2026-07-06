"""OpenAPI / Swagger source-type ingestion (feature 050-F).

A structured-render ingestion path for REST API reference content. Unlike the
PDF/DOCX layout pipeline, an OpenAPI/Swagger specification is already a typed
object model; this package traverses the model and renders deterministic
Markdown (one document per operation and per named component schema) that fits
docline's existing ``BaseDocument`` output contract.

v1 scope: OpenAPI 3.x, single-spec, per-operation granularity, local
``#/components/*`` ``$ref`` resolution only.
"""
