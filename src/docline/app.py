"""Application-level functions shared between CLI and MCP server."""

from docline.app_models import FetchRequest, Manifest, ManifestTool, ProcessRequest


def get_manifest() -> Manifest:
    """Build and return the docline tool manifest.

    Derives tool parameter schemas from the Pydantic model JSON schemas for
    :class:`~docline.app_models.FetchRequest` and
    :class:`~docline.app_models.ProcessRequest`.

    Returns:
        A :class:`~docline.app_models.Manifest` containing ``fetch`` and
        ``process`` tool definitions.
    """
    fetch_schema = FetchRequest.model_json_schema()
    process_schema = ProcessRequest.model_json_schema()

    fetch_props = fetch_schema.get("properties", {})
    process_props = process_schema.get("properties", {})

    return Manifest(
        tools=[
            ManifestTool(
                name="fetch",
                description=(
                    "Fetch a document from a URL or file path and stage it for processing."
                ),
                parameters=fetch_props,
            ),
            ManifestTool(
                name="process",
                description=("Process staged documents into schema-validated Markdown output."),
                parameters=process_props,
            ),
        ]
    )
