from __future__ import annotations

from simpleconvbot.operations import OperationDefinition

PDF_OPERATIONS = (
    OperationDefinition("pdf.to_images", 1, "pdf"),
    OperationDefinition("pdf.to_jpeg_images", 1, "pdf"),
    OperationDefinition("pdf.from_images", 1, "pdf"),
    OperationDefinition("pdf.merge", 1, "pdf"),
    OperationDefinition("pdf.extract_pages", 1, "pdf"),
)
