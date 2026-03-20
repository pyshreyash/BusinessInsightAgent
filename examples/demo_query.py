from __future__ import annotations

import os

import httpx


async def main() -> None:
    question = os.environ.get("QUESTION", "Why did revenue drop last week?")
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base_url}/api/query",
            json={"question": question},
        )
        resp.raise_for_status()
        print(resp.json())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

