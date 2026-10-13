"""Compatibility CLI: monitoring now reads account balances only."""
import asyncio
from monitor_account import main

if __name__ == '__main__':
    asyncio.run(main())
