"""Check seam deduplication and portable formats independently of the live game."""
import gzip
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys
import zlib

import pytest


def load_materializer():
    path = Path(__file__).resolve().parents[2] / "scripts/materialize_map_export.py"
    spec = importlib.util.spec_from_file_location("materializer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_grid_removes_shared_borders_and_preserves_models(tmp_path, monkeypatch):
    report = {"status": "complete", "files": {}, "counts": {"fatInstances": 0, "thinInstances": 1},
              "info": {"terrain": {"minTileX": -1, "minTileY": -1, "tileColumns": 2,
                                   "tileRows": 2, "baseResolution": {"z": 0.05}, "offsetZ": -100}}}
    (tmp_path / "manifest.json").write_text(json.dumps(report), encoding="utf-8")
    db = sqlite3.connect(tmp_path / "map.sqlite")
    db.executescript("""
      CREATE TABLE terrain_tiles(x,y,side,values_zlib,probes_json);
      CREATE TABLE map_layers(name,width,height);
      CREATE TABLE map_cells(layer,offset,count,values_zlib);
      CREATE TABLE model_entities(id,dynamic,instances_zlib);
    """)
    pack = lambda value: zlib.compress(json.dumps(value).encode())
    for ty in range(2):
        for tx in range(2):
            values = [tx*64+x+(ty*64+y)*129 for y in range(65) for x in range(65)]
            probes = [{"index": i, "height": values[i-1]*0.05-100} for i in (1, 2113, 4225)]
            db.execute("INSERT INTO terrain_tiles VALUES (?,?,?,?,?)", (tx-1, ty-1, 65, pack(values), json.dumps(probes)))
    db.execute("INSERT INTO map_layers VALUES ('forest_mask',3,2)")
    db.execute("INSERT INTO map_cells VALUES ('forest_mask',0,4,?)", (pack([0, 1, 2, 3]),))
    db.execute("INSERT INTO map_cells VALUES ('forest_mask',4,2,?)", (pack([4, 5]),))
    db.execute("INSERT INTO model_entities VALUES (7,0,?)", (pack({"fat": [], "thin": [{"modelName": "tree.mdl", "pos": {"x": 1, "y": 2, "z": 3}}]}),))
    db.commit()
    db.close()
    monkeypatch.setattr(sys, "argv", ["materialize", str(tmp_path)])
    load_materializer().main()
    with gzip.open(tmp_path / "terrain_base_4m.f32.gz", "rb") as stream:
        data = stream.read()
    heights = struct.unpack("<" + "f"*(129*129), data)
    assert heights[0] == -100
    assert heights[64] == pytest.approx(-96.8)
    assert heights[-1] == pytest.approx((129*129-1)*0.05-100)
    with gzip.open(tmp_path / "model_instances.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == 1 and rows[0]["entity"] == 7 and rows[0]["modelName"] == "tree.mdl"
    verified = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert verified["terrainGrid"]["samples"] == 16641
    assert verified["terrainGrid"]["sharedBordersVerified"]


def test_materializer_rejects_incomplete_exports(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text('{"status":"failed"}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["materialize", str(tmp_path)])
    with pytest.raises(RuntimeError, match="incomplete"):
        load_materializer().main()
