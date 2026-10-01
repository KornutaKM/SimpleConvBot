from __future__ import annotations

from simpleconvbot.operations import OperationDefinition

MEDIA_OPERATIONS = (
    OperationDefinition("audio.to_mp3", 1, "media"),
    OperationDefinition("audio.to_m4a", 1, "media"),
    OperationDefinition("audio.to_wav", 1, "media"),
    OperationDefinition("video.to_mp3", 1, "media"),
    OperationDefinition("video.mute", 1, "media"),
    OperationDefinition("video.to_gif", 1, "media"),
    OperationDefinition("video.compress_best", 1, "media"),
    OperationDefinition("video.compress_balanced", 1, "media"),
    OperationDefinition("video.compress_smallest", 1, "media"),
    OperationDefinition("video.compress", 1, "media"),
)
