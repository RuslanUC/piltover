#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.
import glob
import os
import py_compile
import re
import shutil
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import NamedTuple
from zipfile import ZipFile

from tqdm import tqdm

CONSTRUCTORS_IN_SEPARATE_FILES = False

HOME_PATH = Path("./tools")
DESTINATION_PATH = Path("piltover/tl")

SECTION_RE = re.compile(r"---(\w+)---")
LAYER_RE = re.compile(r"//\sLAYER\s(\d+)")
COMBINATOR_RE = re.compile(r"^([\w.]+)#([0-9a-f]+)\s(?:.*)=\s([\w<>.]+);$", re.MULTILINE)
ARGS_RE = re.compile(r"[^{](\w+):([\w?!.<>#]+)")
FLAGS_RE = re.compile(r"flags(\d?)\.(\d+)\?")
FLAGS_RE_3 = re.compile(r"flags(\d?):#")

CORE_TYPES = {"int", "long", "int128", "int256", "double", "bytes", "string", "Bool", "true", "#"}
CORE_TYPES_D = {"int": "Int", "#": "Int", "long": "Long", "int128": "Int128", "int256": "Int256"}

WARNING = """
# # # # # # # # # # # # # # # # # # # # # # # #
#               !!! WARNING !!!               #
#          This is a generated file!          #
# All changes made in this file will be lost! #
# # # # # # # # # # # # # # # # # # # # # # # #
""".strip()

# noinspection PyShadowingBuiltins
open_ = open
open = partial(open, encoding="utf-8")

all_layers = set()
types_to_constructors = {"future_salt": ["FutureSalt"]}
types_to_functions = {}
namespaces_to_types = {}
namespaces_to_constructors = defaultdict(list)
namespaces_to_functions = defaultdict(list)


class Combinator(NamedTuple):
    section: str
    qualname: str
    namespace: str
    name: str
    id: str
    has_flags: bool
    args: list[tuple[str, str]]
    qualtype: str
    typespace: str
    type: str
    layer: int = 0


def snake(s: str):
    # https://stackoverflow.com/q/1175208
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def camel(s: str):
    return "".join([i[0].upper() + i[1:] for i in s.split("_")])


def layer_suffix(type_: str, layer: int) -> str:
    found_layer = 0
    for try_layer in range(layer, min(all_layers) - 1, -1):
        if f"{type_}_{try_layer}" in types_to_constructors:
            found_layer = try_layer
            break

    return f"_{found_layer}" if found_layer else ""


# noinspection PyShadowingBuiltins, PyShadowingNames
def get_type_hint(type: str, layer: int, int_is_int: bool = False) -> str:
    is_flag = FLAGS_RE.match(type)
    is_core = False

    if is_flag:
        type = type.split("?")[1]

    if type in CORE_TYPES:
        is_core = True

        if type == "long" or type == "#" or "int" in type:
            type = "int" if int_is_int else CORE_TYPES_D.get(type, "Int")
        elif type == "double":
            type = "float"
        elif type == "string":
            type = "str"
        elif type in ["Bool", "true"]:
            type = "bool"
        else:  # bytes and object
            type = "bytes"

    if type in ["Object", "!X"]:
        return "TLObject"

    if re.match("^vector", type, re.I):
        is_core = True

        sub_type = type.split("<")[1][:-1]
        type = f"list[{get_type_hint(sub_type, layer, int_is_int)}]"

    if is_core:
        return f"Optional[{type}]" if is_flag and type != "bool" else type
    else:
        base_type = f"{type}{layer_suffix(type, layer)}"
        constructors = types_to_constructors[base_type]
        type = ", ".join([f"types.{constr}" for constr in constructors])
        type = f"Union[{type}]" if len(constructors) > 1 else type

        return f"Optional[{type}]" if is_flag else type


def is_tl_object(field_type: str) -> bool:
    if field_type in CORE_TYPES or re.match("^vector", field_type, re.I):
        return False

    return True


def sort_args(args):
    """Put flags at the end"""
    args = args.copy()
    flags = [i for i in args if FLAGS_RE.match(i[1])]

    for i in flags:
        args.remove(i)

    for i in args[:]:
        if re.match(r"flags\d?", i[0]) and i[1] == "#":
            args.remove(i)

    return args + flags


def parse_schema(schema: list[str], layer_: int | None = None) -> tuple[list[Combinator], int]:
    combinators = []
    layer = None
    section = None

    for line in tqdm(schema, desc=f"Parsing schema for layer {layer_ or '?'}", leave=False):
        # Check for section changer lines
        section_match = SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1)
            continue

        # Save the layer version
        layer_match = LAYER_RE.match(line)
        if layer_match:
            layer = int(layer_match.group(1))
            continue

        combinator_match = COMBINATOR_RE.match(line)
        if combinator_match:
            # noinspection PyShadowingBuiltins
            qualname, id, qualtype = combinator_match.groups()

            namespace, name = qualname.split(".") if "." in qualname else ("", qualname)
            name = camel(name)
            qualname = ".".join([namespace, name]).lstrip(".")

            typespace, type = qualtype.split(".") if "." in qualtype else ("", qualtype)
            type = camel(type)
            qualtype = ".".join([typespace, type]).lstrip(".")

            # Pingu!
            has_flags = not not FLAGS_RE_3.findall(line)

            args: list[tuple[str, str]] = ARGS_RE.findall(line)

            # Fix arg name being "self" (reserved python keyword)
            for i, item in enumerate(args):
                if item[0] == "self":
                    args[i] = ("is_self", item[1])
                elif item[0] == "from":
                    args[i] = ("from_", item[1])
                elif item[0] in ("bytes", "str", "type"):
                    args[i] = (f"{item[0]}_", item[1])

            combinator = Combinator(
                section=section,
                qualname=qualname,
                namespace=namespace,
                name=name,
                id=f"0x{id}",
                has_flags=has_flags,
                args=args,
                qualtype=qualtype,
                typespace=typespace,
                type=type
            )

            combinators.append(combinator)

    if layer is not None:
        all_layers.add(layer)
    return combinators, layer


def parse_old_schemas(schemaBase: list[Combinator]) -> dict[int, dict[str, Combinator]]:
    schemaBase = {f"{c.qualname}#{c.id}": c for c in schemaBase}

    layers = sorted([
        int(file[4:-3])
        for file in os.listdir(HOME_PATH / "resources")
        if file.startswith("api_") and file.endswith(".tl")
    ])

    schemas: dict[int, dict[str, Combinator]] = {}
    for layer in layers:
        with open(HOME_PATH / f"resources/api_{layer}.tl") as f:
            parsed = parse_schema(f.read().splitlines(), layer)[0]

        schemas[layer] = {}
        for c in parsed:
            name = f"{c.qualname}#{c.id}"
            if name in schemaBase:
                continue
            c = c._replace(layer=layer)
            schemas[layer][name] = c

    for i in range(len(layers)):
        for cname in schemas[layers[i]]:
            for j in range(i + 1, len(layers)):
                if cname in schemas[layers[j]]:
                    del schemas[layers[j]][cname]

    for layer in layers:
        if len(schemas[layer]) == 0:
            del schemas[layer]
            continue
        for cname in schemas[layer]:
            c = schemas[layer][cname]
            replacements = {
                "qualname": f"{c.qualname}_{layer}",
                "qualtype": f"{c.qualtype}_{layer}",
                "name": f"{c.name}_{layer}",
                "type": f"{c.type}_{layer}",
            }
            schemas[layer][cname] = c._replace(**replacements)

    return schemas


def parse_old_objects(schemaBase: list[Combinator]) -> list[Combinator]:
    result = []
    for schema in parse_old_schemas(schemaBase).values():
        result.extend(schema.values())

    return result


def indent(lines: list[str], spaces: int) -> list[str]:
    return [" " * spaces + line for line in lines]


class Field:
    _COUNTER = 0

    __slots__ = ("position", "name", "is_flag", "flag_bit", "flag_num", "full_type", "write",)

    def __init__(
            self, name: str, is_flag: bool = False, flag_bit: int | None = None, flag_num: int | None = None,
            type_: str = None, write: bool = True,
    ):
        self.position = self.__class__._COUNTER
        self.__class__._COUNTER += 1
        self.name = name
        self.is_flag = is_flag
        self.flag_bit = flag_bit
        self.flag_num = flag_num
        self.full_type = type_
        self.write = write

    def opt(self) -> bool:
        return self.flag_bit is not None and not self.is_flag

    def type(self) -> str:
        return self.full_type if "?" not in self.full_type else self.full_type.split("?", 1)[1]


# noinspection PyShadowingBuiltins
def start():
    shutil.rmtree(DESTINATION_PATH / "types", ignore_errors=True)
    shutil.rmtree(DESTINATION_PATH / "functions", ignore_errors=True)

    schema = []
    for file_name in os.listdir(HOME_PATH / "resources"):
        if file_name.startswith("api_") or not file_name.endswith(".tl"):
            continue
        with open(HOME_PATH / "resources" / file_name) as f:
            schema.extend(f.read().splitlines())

    combinators, layer = parse_schema(schema)
    combinators.extend(parse_old_objects(combinators))

    for c in tqdm(combinators, desc="Processing combinators", total=len(combinators)):
        qualtype = c.qualtype

        if qualtype.startswith("Vector"):
            qualtype = qualtype.split("<")[1][:-1]

        d = types_to_constructors if c.section == "types" else types_to_functions

        if qualtype not in d:
            d[qualtype] = []

        d[qualtype].append(c.qualname)

    for c in tqdm(combinators, desc="Writing combinators", total=len(combinators)):
        fields = []
        flag_num = 1
        for arg in c.args:
            fields.append((field := Field(arg[0])))

            arg_type = arg[1]
            if arg_type == "#":
                field.is_flag = True
                field.flag_num = flag_num
                flag_num += 1
            if "?" in arg_type:
                bit = int(arg_type.split(".")[1].split("?")[0])
                this_flag_num = arg_type.split("?")[0].split(".")[0][5:]

                field.flag_bit = bit
                field.flag_num = int(this_flag_num) if this_flag_num else 1
                field.write = arg_type.split("?")[1] != "true"

                arg_type = arg_type.split("?", 1)[1]

            field.full_type = arg_type

        third_dot = "." if "." in c.qualname else ""
        slots = [f"\"{field.name}\"" for field in fields if not field.is_flag]
        slots.append("")  # For trailing comma

        init_args = [
            f"{field.name}: {get_type_hint(field.full_type, c.layer, True)}"
            + ("" if not field.opt() else (" = False" if field.type() in ("true", "Bool") else " = None"))
            for field in sorted(fields, key=lambda fd: (fd.opt(), fd.position))
            if not field.is_flag
        ]
        if init_args:
            init_args.insert(0, "*")

        deserialize_cls_args = [
            f"{field.name}={field.name}"
            for field in fields if not field.is_flag
        ]

        serialize_body = []
        deserialize_body = []
        for field in fields:
            tmp_ = field.type().split("Vector<")
            is_vec = len(tmp_) > 1

            int_type = CORE_TYPES_D.get(field.type().lower(), None)
            int_subtype = None
            if is_vec and int_type is None:
                int_subtype = CORE_TYPES_D.get(tmp_[1].lower().split(">")[0], None)

            int_type_name = (int_subtype if int_subtype is not None else int_type) or ""
            if int_type_name:
                int_type_name = f", {int_type_name}"

            subtype_name = None
            if is_vec:
                type_name = "list"
                tmp_ = tmp_[1].split(">")[0]
                if is_tl_object(tmp_):
                    subtype_name = "TLObject"
                else:
                    subtype_name = get_type_hint(tmp_, c.layer)
            else:
                tmp_ = tmp_[0]
                if is_tl_object(field.type()):
                    type_name = "TLObject"
                else:
                    type_name = get_type_hint(tmp_, c.layer)

            subtype_name = f", {subtype_name}" if subtype_name is not None else ""

            if field.is_flag:
                flag_var = f"flags{field.flag_num}"
                serialize_body.append(f"{flag_var} = 0")
                for ffield in fields:
                    if not ffield.opt() or ffield.flag_num != field.flag_num:
                        continue
                    empty_condition = "" if ffield.type().lower().startswith("vector") or not ffield.write else " is not None"
                    serialize_body.append(f"if self.{ffield.name}{empty_condition}: {flag_var} |= (1 << {ffield.flag_bit})")
                serialize_body.append(f"result += SerializationUtils.write({flag_var}, Int)")

                deserialize_body.append(f"{flag_var} = SerializationUtils.read(stream, Int)")
                continue

            if field.opt():
                if field.write:
                    empty_condition = ""
                    fields_with_this_flag = len([
                        1 for f in fields if f.flag_num == field.flag_num and f.flag_bit == field.flag_bit
                    ])
                    if fields_with_this_flag > 1 or not field.type().lower().startswith("vector"):
                        empty_condition = " is not None"

                    serialize_body.append(f"if self.{field.name}{empty_condition}:")
                    serialize_body.append(f"    result += SerializationUtils.write(self.{field.name}{int_type_name})")
                    deserialize_body.append(
                        f"{field.name} = SerializationUtils.read(stream, {type_name}{subtype_name}) "
                        f"if (flags{field.flag_num} & (1 << {field.flag_bit})) == (1 << {field.flag_bit}) else None"
                    )
                elif field.type() == "true":
                    deserialize_body.append(
                        f"{field.name} = (flags{field.flag_num} & (1 << {field.flag_bit})) == (1 << {field.flag_bit})"
                    )

                continue

            serialize_body.append(f"result += SerializationUtils.write(self.{field.name}{int_type_name})")
            deserialize_body.append(f"{field.name} = SerializationUtils.read(stream, {type_name}{subtype_name})")

        imports = [
            f"from __future__ import annotations",
            f"from typing import Optional, Union",
            f"from {third_dot}..primitives import *",
            f"from {third_dot}.. import types, SerializationUtils",
            f"from {third_dot}..tl_object import TLObject",
        ]
        result = [
            f"",
            f"",
            f"class {c.name}(TLObject):",
            f"    __tl_id__ = {c.id}",
            f"    __tl_name__ = \"{c.section}.{c.qualname}\"",
            f"",
            f"    __slots__ = ({', '.join(slots)})",
            f"",
            f"    def __init__(self{', ' if init_args else ''}{', '.join(init_args)}):",
            f"        ..." if not init_args else f"",
            *[
                f"        self.{field.name} = {field.name}"
                for field in fields if not field.is_flag
            ],
            f"",
            f"    def serialize(self) -> bytes:",
            f"        result = b\"\"",
            *indent(serialize_body, 8),
            f"        return result",
            f"",
            f"    @classmethod",
            f"    def deserialize(cls, stream) -> {c.name}:",
            *indent(deserialize_body, 8),
            f"        return cls({', '.join(deserialize_cls_args)})",
            f"",
        ]

        dir_path = DESTINATION_PATH / c.section / c.namespace
        dir_path.mkdir(parents=True, exist_ok=True)

        if CONSTRUCTORS_IN_SEPARATE_FILES:
            module = c.name if c.name != "Updates" else "UpdatesT"
            out_path = dir_path / f"{snake(module)}.py"
            with open(out_path, "w") as f:
                f.write("\n".join(imports))
                f.write("\n".join(result))
        else:
            out_path = dir_path / f"__init__.py"
            if not out_path.exists():
                with open(out_path, "w") as f:
                    f.write("\n".join(imports))
            with open(out_path, "a") as f:
                f.write("\n".join(result))

        d = namespaces_to_constructors if c.section == "types" else namespaces_to_functions
        d[c.namespace].append(c.name)

    for namespace, types in namespaces_to_constructors.items():
        out_path = DESTINATION_PATH / "types" / namespace / "__init__.py"

        if CONSTRUCTORS_IN_SEPARATE_FILES:
            with open(out_path, "w") as f:
                f.write(f"{WARNING}\n\n")

                for t in types:
                    module = t

                    if module == "Updates":
                        module = "UpdatesT"

                    f.write(f"from .{snake(module)} import {t}\n")

                if not namespace:
                    f.write(f"from . import {', '.join(filter(bool, namespaces_to_constructors))}\n")
        elif not namespace:
            with open(out_path, "a") as f:
                f.write(f"\nfrom . import {', '.join(filter(bool, namespaces_to_constructors))}\n")

    for namespace, types in namespaces_to_functions.items():
        out_path = DESTINATION_PATH / "functions" / namespace / "__init__.py"

        if CONSTRUCTORS_IN_SEPARATE_FILES:
            with open(out_path, "w") as f:
                f.write(f"{WARNING}\n\n")

                for t in types:
                    module = t

                    if module == "Updates":
                        module = "UpdatesT"

                    f.write(f"from .{snake(module)} import {t}\n")

                if not namespace:
                    f.write(f"from . import {', '.join(filter(bool, namespaces_to_functions))}")
        elif not namespace:
            with open(out_path, "a") as f:
                f.write(f"\nfrom . import {', '.join(filter(bool, namespaces_to_functions))}\n")

    with open(DESTINATION_PATH / "all.py", "w", encoding="utf-8") as f:
        f.write(WARNING + "\n\n")
        f.write(f"from . import core_types, types, functions\n\n")
        f.write(f"min_layer = {min(all_layers)}\n")
        f.write(f"layer = {layer}\n\n")
        f.write("objects = {")

        for c in combinators:
            f.write(f'\n    {c.id}: {c.section}.{c.qualname},')

        f.write(f'\n    0x5bb8e511: core_types.Message,')
        f.write(f'\n    0x73f1f8dc: core_types.MsgContainer,')
        f.write(f'\n    0xf35c6d01: core_types.RpcResult,')
        f.write(f'\n    0x3072cfa1: core_types.GzipPacked,')

        f.write("\n}\n")


if "__main__" == __name__:
    start()
