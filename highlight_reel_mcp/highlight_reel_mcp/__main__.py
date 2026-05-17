import asyncio

from mcp.server.stdio import stdio_server

from .server import server


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


asyncio.run(main())
