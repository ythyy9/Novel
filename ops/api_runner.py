"""Immutable deployment runner; candidate source remains a separate PYTHONPATH."""
import os
from backend.api import create_app
import uvicorn

app = create_app()


class ReleaseIdentity:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    async def __call__(self, scope, receive, send):
        async def with_release(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-novel-release", os.environ["NOVEL_RELEASE"].encode()))
            await send(message)
        await self.wrapped(scope, receive, with_release)


if __name__ == "__main__":
    uvicorn.run(ReleaseIdentity(app), host="127.0.0.1", port=int(os.environ["NOVEL_PORT"]),
                proxy_headers=True, forwarded_allow_ips="127.0.0.1", access_log=False,
                timeout_graceful_shutdown=90)
