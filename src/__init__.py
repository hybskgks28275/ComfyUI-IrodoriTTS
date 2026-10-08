from comfy_api.latest import ComfyExtension, io

from .nodes.generate import IrodoriTTSGenerate
from .nodes.audio_save import IrodoriTTSSaveAudio
from .nodes.reference_audio import IrodoriTTSLoadReferenceAudios

class IrodoriTTSExtension(ComfyExtension):
    async def on_load(self):
        from server import PromptServer
        from .modules.routes import release_runtime
        PromptServer.instance.routes.post("/irodori_tts/release")(release_runtime)

    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [IrodoriTTSGenerate, IrodoriTTSLoadReferenceAudios, IrodoriTTSSaveAudio]


async def comfy_entrypoint() -> ComfyExtension:
    return IrodoriTTSExtension()


__all__ = ["comfy_entrypoint"]
