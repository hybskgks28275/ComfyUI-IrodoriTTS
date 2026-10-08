import asyncio

from aiohttp import web

from ..nodes.generate import release_cached_runtime


async def release_runtime(request):
    # Collection and CUDA cleanup must not block ComfyUI's HTTP event loop.
    status = await asyncio.to_thread(release_cached_runtime)
    return web.json_response({"status": status}, status=409 if status == "busy" else 200)
