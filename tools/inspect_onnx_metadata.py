#!/usr/bin/env python3
"""Read-only ONNX metadata inventory without executing models or loading pickle.

Uses a bounded subset of the official ONNX protobuf schema:
https://github.com/onnx/onnx/blob/main/onnx/onnx.proto
This is not an ONNX checker, shape inference, or TensorRT compatibility test.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct


def varint(data, offset):
    result = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Truncated protobuf varint")
        byte = data[offset]
        offset += 1
        result |= (byte & 127) << shift
        if byte < 128:
            if result >= 1 << 64:
                raise ValueError("Oversized protobuf varint")
            return result, offset
    raise ValueError("Invalid protobuf varint")


def fields(data):
    offset = 0
    while offset < len(data):
        key, offset = varint(data, offset)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ValueError("Invalid protobuf field")
        if wire == 0:
            value, offset = varint(data, offset)
        else:
            if wire == 2:
                size, offset = varint(data, offset)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                raise ValueError("Unsupported protobuf wire type")
            if size > len(data) - offset:
                raise ValueError("Truncated protobuf field")
            value = data[offset:offset + size]
            offset += size
        yield number, wire, value


def values(data, number):
    return [value for field, _, value in fields(data) if field == number]


def first(data, number, default=None):
    return next((value for field, _, value in fields(data) if field == number), default)


def text(value):
    return bytes(value).decode("utf-8") if value is not None else ""


def tensor_info(value):
    tensor = first(first(value, 2, b""), 1)
    if tensor is None:
        return {"name": text(first(value, 1)), "type": "non-tensor/unspecified"}
    shape = []
    for dim in values(first(tensor, 2, b""), 1):
        size = first(dim, 1)
        shape.append(size if size is not None else text(first(dim, 2)) or None)
    dtype = first(tensor, 1)
    labels = {1: "FLOAT32", 2: "UINT8", 3: "INT8", 4: "UINT16", 5: "INT16",
              6: "INT32", 7: "INT64", 8: "STRING", 9: "BOOL", 10: "FLOAT16",
              11: "FLOAT64", 12: "UINT32", 13: "UINT64"}
    return {"name": text(first(value, 1)), "dtype_id": dtype,
            "dtype": labels.get(dtype, "other"), "shape": shape}


def attribute_info(data):
    result = {"name": text(first(data, 1)), "type_id": first(data, 20)}
    kind = result["type_id"]
    if kind == 1:
        raw = first(data, 2)
        result["value"] = struct.unpack("<f", raw)[0] if raw is not None else None
    elif kind == 2:
        value = first(data, 3)
        result["value"] = value - (1 << 64) if value is not None and value >= 1 << 63 else value
    elif kind == 3:
        result["value"] = text(first(data, 4))
    elif kind == 6:
        result["value"] = []
        for field, wire, value in fields(data):
            if field == 7:
                if wire == 5:
                    result["value"].append(struct.unpack("<f", value)[0])
                elif wire == 2 and len(value) % 4 == 0:
                    result["value"].extend(item[0] for item in struct.iter_unpack("<f", value))
    elif kind == 7:
        result["value"] = []
        for field, wire, value in fields(data):
            if field != 8:
                continue
            if wire == 0:
                result["value"].append(value)
            elif wire == 2:
                offset = 0
                while offset < len(value):
                    item, offset = varint(value, offset)
                    result["value"].append(item)
    return result


def inspect(path):
    with path.open("rb") as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Metadata inspector caps ONNX files at 16 MiB")
    model = memoryview(data)
    graph = first(model, 7)
    if graph is None:
        raise ValueError("No ONNX graph found")
    nodes = values(graph, 1)
    operators = collections.Counter()
    plugin_nodes = []
    for node in nodes:
        op, domain = text(first(node, 4)), text(first(node, 7))
        operators[(domain + "::" if domain else "") + op] += 1
        if "plugin" in op.lower() or domain not in ("", "ai.onnx", "ai.onnx.ml"):
            plugin_nodes.append({"name": text(first(node, 3)), "op_type": op, "domain": domain,
                                 "inputs": [text(v) for v in values(node, 1)],
                                 "outputs": [text(v) for v in values(node, 2)],
                                 "attributes": [attribute_info(v) for v in values(node, 5)]})
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "ir_version": first(model, 1), "producer": text(first(model, 2)),
            "producer_version": text(first(model, 3)),
            "opsets": [{"domain": text(first(v, 1)), "version": first(v, 2)} for v in values(model, 8)],
            "inputs": [tensor_info(v) for v in values(graph, 11)],
            "outputs": [tensor_info(v) for v in values(graph, 12)],
            "operators": dict(sorted(operators.items())), "plugin_or_custom_domain_nodes": plugin_nodes,
            "validation": "Metadata extraction only; not checked/executed by ONNX or TensorRT. Plugin-name detection is heuristic."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.model), indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"Metadata inspection failed: {error}\n")
