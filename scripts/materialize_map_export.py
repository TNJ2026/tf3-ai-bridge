"""Create portable gzip files from a completed SQLite map export and verify seams."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import zlib


def unpack(blob):
    return json.loads(zlib.decompress(blob))


def main():
    directory = Path(sys.argv[1])
    manifest_path = directory / "manifest.json"
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report["status"] != "complete":
        raise RuntimeError("source export is incomplete")
    db = sqlite3.connect(directory / "map.sqlite")
    info = report["info"]
    terrain = info["terrain"]
    min_x, min_y = terrain["minTileX"], terrain["minTileY"]
    columns, rows = terrain["tileColumns"], terrain["tileRows"]
    scale, offset = terrain["baseResolution"]["z"], terrain["offsetZ"]
    previous = {}
    samples = 0
    max_probe_error = 0
    width = height = None
    terrain_path = directory / "terrain_base_4m.f32.gz"
    with gzip.open(terrain_path, "wb") as output:
        for y in range(min_y, min_y + rows):
            tiles = []
            for x, side, blob, probes in db.execute(
                "SELECT x,side,values_zlib,probes_json FROM terrain_tiles WHERE y=? ORDER BY x", (y,)
            ):
                assert x == min_x + len(tiles)
                data = unpack(blob)
                assert side == 65 and len(data) == side*side
                if tiles:
                    left = tiles[-1]
                    assert all(left[r*side+side-1] == data[r*side] for r in range(side)), "x seam mismatch"
                if x in previous:
                    assert previous[x] == data[:side], "y seam mismatch"
                previous[x] = data[-side:]
                for probe in json.loads(probes):
                    error = abs(data[probe["index"]-1]*scale + offset - probe["height"])
                    max_probe_error = max(max_probe_error, error)
                    assert error < 0.001, "raw height decoding does not match game terrain"
                tiles.append(data)
            assert len(tiles) == columns
            width, height = columns*64+1, rows*64+1
            for row in range(65 if y == min_y+rows-1 else 64):
                values = []
                for col, data in enumerate(tiles):
                    take = 65 if col == columns-1 else 64
                    values.extend(v*scale+offset for v in data[row*65:row*65+take])
                assert len(values) == width
                output.write(struct.pack("<" + "f"*len(values), *values))
                samples += len(values)
    assert samples == width*height
    report["terrainGrid"] = {
        "file": terrain_path.name, "width": width, "height": height, "samples": samples,
        "dtype": "little-endian float32 metres", "spacingMetres": 4,
        "origin": {"x": min_x*256, "y": min_y*256},
        "order": "row-major; x increases east, y increases north",
        "semantics": "native base terrain; excludes non-permanent surface alignments",
        "sharedBordersVerified": True, "maxHeightProbeErrorMetres": max_probe_error,
    }
    portable_layers = {}
    for name, w, h in db.execute("SELECT name,width,height FROM map_layers ORDER BY name").fetchall():
        # Filenames derived from the game's data are constrained to a simple component.
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        path = directory / ("layer_" + safe + ".f32.gz")
        count = 0
        with gzip.open(path, "wb") as output:
            for begin, n, blob in db.execute("SELECT offset,count,values_zlib FROM map_cells WHERE layer=? ORDER BY offset", (name,)):
                values = unpack(blob)
                assert begin == count and len(values) == n
                output.write(struct.pack("<" + "f"*n, *values))
                count += n
        assert count == w*h
        portable_layers[name] = {"file": path.name, "width": w, "height": h, "cells": count,
                                 "dtype": "little-endian float32 raw layer values", "order": "row-major, x fastest"}
    report["portableLayers"] = portable_layers
    model_path = directory / "model_instances.jsonl.gz"
    count = 0
    with gzip.open(model_path, "wt", encoding="utf-8", newline="\n") as output:
        for entity, dynamic, blob in db.execute("SELECT id,dynamic,instances_zlib FROM model_entities ORDER BY id"):
            data = unpack(blob)
            for kind in ("fat", "thin"):
                for index, instance in enumerate(data[kind], start=1):
                    row = {"entity": entity, "dynamic": bool(dynamic), "kind": kind,
                           "index": index, **instance}
                    output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
                    count += 1
    assert count == report["counts"]["fatInstances"] + report["counts"]["thinInstances"]
    report["portableModels"] = {"file": model_path.name, "instances": count, "format": "gzip UTF-8 JSON Lines"}
    db.close()
    for path in sorted(directory.glob("*.gz")):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report["files"][path.name] = {"bytes": path.stat().st_size, "sha256": digest}
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    print(json.dumps({"terrainSamples": samples, "grid": [width, height], "layerCount": len(portable_layers),
                      "modelInstances": count, "maxHeightProbeErrorMetres": max_probe_error}, indent=2))


if __name__ == "__main__":
    main()
