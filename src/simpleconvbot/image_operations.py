from __future__ import annotations

from simpleconvbot.operations import OperationDefinition

IMAGE_OPERATIONS = (
    OperationDefinition("image.to_jpeg", 1, "image"),
    OperationDefinition("image.to_png", 1, "image"),
    OperationDefinition("image.to_webp", 1, "image"),
    OperationDefinition("image.compress", 1, "image"),
    OperationDefinition("image.resize_25", 1, "image"),
    OperationDefinition("image.resize_50", 1, "image"),
    OperationDefinition("image.resize_720", 1, "image"),
    OperationDefinition("image.resize_1080", 1, "image"),
)
