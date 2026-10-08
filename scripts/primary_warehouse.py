"""Shared local Lua audit and canonical inventory accounting. No game calls here."""
from pathlib import Path

def selection(value):
    if value is None:return 'nil'
    if type(value)is not int or value<0:raise ValueError('Invalid primary stock-list ID')
    return str(value)

def prelude():
    return Path(__file__).with_suffix('.lua').read_text('utf8')+'\n'

def inventory_totals(audits):
    """One capacity entry per actual stock-list ID across reused collections."""
    inventory={}
    for audit in audits:
        for key,row in audit['inventoryById'].items():
            sid=int(key)
            if row['stockList']!=sid:raise ValueError('Inventory identity mismatch')
            if sid in inventory and inventory[sid]!=row:
                raise ValueError('Inventory changed between reads; recollect instead of summing')
            inventory[sid]=row
    return {'inventoryIds':sorted(inventory),'capacity':sum(r['capacity']for r in inventory.values()),
            'quantity':sum(r['quantity']for r in inventory.values())if all('quantity'in r for r in inventory.values())else None}
