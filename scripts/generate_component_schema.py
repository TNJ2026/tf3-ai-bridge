"""Generate nested component field schemas from the game's bundled Teal definitions.

Usage: python scripts/generate_component_schema.py <TF3 installation>/api/tealdef
Replaces only the marked schema block; installs the Lua file atomically.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "-- BEGIN GENERATED COMPONENT SCHEMAS"
END = "-- END GENERATED COMPONENT SCHEMAS"


def parse_records(paths):
    records = {}
    for path in paths:
        stack = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(\s*)(?:global )?record (\w+)", line)
            if match:
                indent = len(match[1].expandtabs(4))
                while stack and stack[-1][0] >= indent:
                    stack.pop()
                name = ".".join([s[1] for s in stack] + [match[2]])
                records.setdefault(name, {})
                stack.append((indent, match[2], name))
                continue
            match = re.match(r"^(\s*)(\w+)\s*:\s*(.+?)\s*$", line)
            if not match or not stack:
                continue
            indent = len(match[1].expandtabs(4))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack and indent == stack[-1][0] + 4:
                field, kind = match[2], match[3]
                if not kind.startswith("function") and not field.endswith("_native"):
                    records[stack[-1][2]][field] = kind
    return records


def descriptor(kind, scope, records):
    kind = kind.strip()
    if kind.startswith("{") and kind.endswith("}"):
        inner = kind[1:-1].strip()
        depth = 0
        for index, char in enumerate(inner):
            depth += (char == "{") - (char == "}")
            if depth == 0 and char == ":":
                inner = inner[index + 1:]
                break
            if depth == 0 and char == ",":
                return ""  # heterogeneous tuple: no record hint
        return {"element": descriptor(inner, scope, records)}
    parts = scope.split(".")
    for length in range(len(parts), -1, -1):
        candidate = ".".join(parts[:length] + [kind])
        if candidate in records:
            fields = records[candidate]
            # Enum constants are not instance fields.
            if fields and all(value == candidate.split(".")[-1] for value in fields.values()):
                return ""
            return candidate
    return ""


def lua(value):
    if isinstance(value, str):
        return json.dumps(value)
    return "{ " + ", ".join("[" + lua(k) + "] = " + lua(v) for k, v in value.items()) + " }"


def main():
    api = Path(sys.argv[1])
    records = parse_records([api / "api/engine.d.tl", api / "api/type.d.tl"])
    target = ROOT / "mod/tf3_mcp_bridge/content/tf3_mcp_bridge/bridge.script.lua"
    source = target.read_text(encoding="utf-8")
    # The top-level allowlist remains explicit and reviewable.
    field_block = source.split("local COMPONENT_FIELDS = {", 1)[1].split("\n}", 1)[0]
    names = re.findall(r"^\s*([A-Z_]+) =", field_block, re.M)
    roots = {}
    for name in names:
        roots[name] = "Station" if name == "STATION" else next(
            key for key in records
            if key.startswith("Engine.Component.") and key.count(".") == 2
            and re.sub(r"(?<!^)(?=[A-Z])", "_", key.split(".")[-1]).upper() == name
        )
    schemas = {}

    def visit(hint):
        if isinstance(hint, dict):
            visit(hint["element"])
        elif hint and hint not in schemas:
            schemas[hint] = {field: descriptor(kind, hint, records) for field, kind in records[hint].items()}
            for child in schemas[hint].values():
                visit(child)

    for name in roots.values():
        visit(name)
    block = START + "\nlocal COMPONENT_RECORDS = " + lua(roots) + "\nlocal RECORD_SCHEMAS = {\n"
    block += "\n".join("\t[" + lua(name) + "] = " + lua(fields) + "," for name, fields in sorted(schemas.items()))
    block += "\n}\n" + END
    if START in source:
        before, rest = source.split(START, 1)
        source = before + block + rest.split(END, 1)[1]
    else:
        source = source.replace("local function readField(v, key)", block + "\n\nlocal function readField(v, key)", 1)
    temporary = target.with_suffix(".lua.tmp")
    temporary.write_text(source, encoding="utf-8")
    os.replace(temporary, target)
    print(f"Generated {len(schemas)} record schemas for {len(roots)} components")


if __name__ == "__main__":
    main()
