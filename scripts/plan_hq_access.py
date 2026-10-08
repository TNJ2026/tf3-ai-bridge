"""Guarded entry point; legacy two-proposal diagnostic removed after native crashes."""
import asyncio
from hq_access_probe import Bridge, analyze, main, prepare

if __name__ == "__main__":
    asyncio.run(main())
