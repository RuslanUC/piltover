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
from __future__ import annotations

import os
import re
import shutil
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Literal, TextIO, Any, cast

from tqdm import tqdm

from tl_gen_placeholders import PLACEHOLDERS
from tl_gen_replace_constructors import REPLACE_CONSTRUCTORS, BASE_CLASSES_NEED_CONTEXT

DRY_RUN = False
HOME_PATH = Path("./tools")
DESTINATION_PATH = Path("piltover/tl")

SECTION_RE = re.compile(r"---(\w+)---")
LAYER_RE = re.compile(r"//\sLAYER\s(\d+)")
COMBINATOR_RE = re.compile(r"^([\w.]+)#([0-9a-f]+)\s.*=\s([\w<>.]+);$", re.MULTILINE)
# COMBINATOR_FOR_CRC_RE = re.compile(
#     r"^(?P<name>[\w.]+)(#[0-9a-f]{1,8})?\s*(?P<fields>.*?)\s*=\s*(?P<typename>[\w<>.]+);$", re.MULTILINE,
# )
ARGS_RE = re.compile(r"[^{](\w+):([\w?!.<>#]+)")
FLAGS_RE = re.compile(r"flags(\d?)\.(\d+)\?")

CORE_TYPES = {"int", "long", "int128", "int256", "double", "bytes", "string", "Bool", "true", "#"}
CORE_TYPES_D = {"int": "Int", "#": "Int", "long": "Long", "int128": "Int128", "int256": "Int256"}

WARNING = """
# # # # # # # # # # # # # # # # # # # # # # # #
#               !!! WARNING !!!               #
#          This is a generated file!          #
# All changes made in this file will be lost! #
# # # # # # # # # # # # # # # # # # # # # # # #
""".strip()

if DRY_RUN:
    __real_open = open

    # noinspection PyShadowingBuiltins
    def open(filename: os.PathLike, mode: Literal["r", "w", "a"] = "r", *args, **kwargs) -> TextIO:
        if mode == "r":
            return __real_open(filename, mode, *args, encoding="utf-8", **kwargs)

        return StringIO()


all_layers = set()
types_to_constructors: dict[str, list[str]] = defaultdict(list)
types_to_constructors["future_salt"].append("FutureSalt")
types_to_combinators: dict[str, list[Combinator]] = defaultdict(list)
namespaces_to_constructors: dict[str, list[str]] = defaultdict(list)
namespaces_to_functions: dict[str, list[str]] = defaultdict(list)
namespaces_to_types: dict[str, list[str]] = defaultdict(list)


class Combinator:
    __slots__ = (
        "section", "qualname", "namespace", "name", "id", "args", "qualtype", "typespace", "type", "fields", "layer",
        "fields_for_check", "min_layer",
    )

    def __init__(
            self, section: str, qualname: str, namespace: str, name: str, id: str, args: list[tuple[str, str]],
            qualtype: str, typespace: str, type_: str
    ) -> None:
        self.section = section
        self.qualname = qualname
        self.namespace = namespace
        self.name = name
        self.id = id
        self.args = args
        self.qualtype = qualtype
        self.typespace = typespace
        self.type = type_
        self.fields: list[Field] = []
        self.layer = 0
        self.min_layer = 0
        self.fields_for_check: list[Field] | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, section={self.section!r}, qualname={self.qualname!r})"


class Field:
    _COUNTER = 0

    __slots__ = ("position", "name", "flag_bit", "flag_num", "full_type", "min_layer", "max_layer",)

    def __init__(
            self, name: str, flag_bit: int | None = None, flag_num: int | None = None, type_: str | None = None,
            min_layer: int | None = None, max_layer: int | None = None
    ) -> None:
        self.position = self.__class__._COUNTER
        self.__class__._COUNTER += 1
        self.name = name
        self.flag_bit = flag_bit
        self.flag_num = flag_num
        self.full_type = cast(str, type_)
        self.min_layer = min_layer
        self.max_layer = max_layer

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Field):
            return False
        return (
                self.name == other.name
                and self.flag_bit == other.flag_bit
                and self.flag_num == other.flag_num
                and self.full_type == other.full_type
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, type={self.full_type!r})"

    def type(self) -> str:
        return self.full_type if "?" not in self.full_type else self.full_type.split("?", 1)[1]

    @property
    def is_flag(self) -> bool:
        return self.full_type == "#"

    @property
    def is_optional(self) -> bool:
        return self.flag_bit is not None and not self.is_flag

    @property
    def is_vector(self) -> bool:
        return self.type().lower().startswith("vector<")

    @property
    def write(self) -> bool:
        return self.type() != "true"

    @property
    def actual_type(self) -> str:
        if self.is_vector:
            return self.type()[7:-1]
        return self.type()

    @property
    def tl_type(self) -> str:
        if self.is_flag:
            return "#"
        if self.flag_bit is None:
            return self.full_type
        return f"flags{self.flag_num if self.flag_num > 1 else ''}.{self.flag_bit}?{self.full_type}"


class CombinatorDiff:
    __slots__ = ("base", "old", "deleted", "added",)

    def __init__(self, base: Combinator, old: Combinator, deleted: list[Field], added: list[Field]) -> None:
        self.base = base
        self.old = old
        self.deleted = deleted
        self.added = added

    def __repr__(self) -> str:
        type_name = self.base.qualname
        if self.base.layer and type_name.endswith(f"_{self.base.layer}"):
            type_name, *_ = type_name.rpartition("_")
        return f"{self.__class__.__name__}(type={type_name!r}, from_layer={self.old.layer}, to_layer={self.base.layer})"


def snake(s: str) -> str:
    # https://stackoverflow.com/q/1175208
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def camel(s: str) -> str:
    return "".join([i[0].upper() + i[1:] for i in s.split("_")])


def layer_suffix(type_: str, layer: int) -> str:
    found_layer = 0
    for try_layer in range(layer, min(all_layers) - 1, -1):
        if f"{type_}_{try_layer}" in types_to_constructors:
            found_layer = try_layer
            break

    return f"_{found_layer}" if found_layer else ""


def get_type_hint(
        type_: str, layer: int, int_is_int: bool = False, dont_use_base_when_only_one_constructor: bool = False,
        use_iterable_for_vector: bool = False, force_optional: bool = False
) -> str:
    is_flag = force_optional or FLAGS_RE.match(type_)
    is_core = False

    if is_flag and not force_optional:
        print(type_)
        type_ = type_.split("?")[1]

    if type_ in CORE_TYPES:
        is_core = True

        if type_ == "long" or type_ == "#" or "int" in type_:
            type_ = "int" if int_is_int else CORE_TYPES_D.get(type_, "Int")
        elif type_ == "double":
            type_ = "float"
        elif type_ == "string":
            type_ = "str"
        elif type_ in ["Bool", "true"]:
            type_ = "bool"
        elif type_ == "bytes":
            pass
        else:
            raise RuntimeError(f"Got unknown type: {type_}")

    if type_ in ["Object", "!X"]:
        return "TLObject"

    if type_.lower().startswith("vector"):
        is_core = True

        sub_type = type_.split("<")[1][:-1]
        outer = "Iterable" if use_iterable_for_vector else "list"
        type_ = f"{outer}[{get_type_hint(sub_type, layer, int_is_int)}]"

    if is_core:
        return f"{type_} | None" if is_flag and type_ != "bool" else type_
    else:
        base_type = f"{type_}{layer_suffix(type_, layer)}"
        if dont_use_base_when_only_one_constructor \
                and base_type in types_to_constructors \
                and len(types_to_constructors[base_type]) == 1:
            type_ = f"tl.types.{types_to_constructors[base_type][0]}"
        else:
            type_ = f"tl.base.{base_type}"

        return f"{type_} | None" if is_flag else type_


def is_tl_object(field_type: str) -> bool:
    if field_type in CORE_TYPES or field_type.lower().startswith("vector"):
        return False

    return True


def parse_schema(schema: list[str], layer_: int | None = None) -> tuple[list[Combinator], int]:
    combinators = []
    layer: int | None = None
    section: str | None = None

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
            qualname, tlid, qualtype = combinator_match.groups()

            namespace, name = qualname.split(".") if "." in qualname else ("", qualname)
            name = camel(name)
            qualname = ".".join([namespace, name]).lstrip(".")

            typespace, type_ = qualtype.split(".") if "." in qualtype else ("", qualtype)
            type_ = camel(type_)
            qualtype = ".".join([typespace, type_]).lstrip(".")

            args: list[tuple[str, str]] = ARGS_RE.findall(line)

            # Fix arg name being "self" (reserved python keyword)
            for i, item in enumerate(args):
                if item[0] == "self":
                    args[i] = ("is_self", item[1])
                # TODO: add "hash"?
                elif item[0] in ("from", "bytes", "str", "type"):
                    args[i] = (f"{item[0]}_", item[1])

            assert section is not None

            combinator = Combinator(
                section=section,
                qualname=qualname,
                namespace=namespace,
                name=name,
                id=f"0x{tlid}",
                args=args,
                qualtype=qualtype,
                typespace=typespace,
                type_=type_,
            )

            combinators.append(combinator)

    assert layer is not None

    for combinator in combinators:
        combinator.min_layer = layer

    all_layers.add(layer)
    return combinators, layer


def parse_old_schemas(combinators_base: list[Combinator]) -> dict[int, dict[str, Combinator]]:
    schema_base = {f"{c.qualname}#{c.id}": c for c in combinators_base}

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
            if name in schema_base:
                obj_base = schema_base[name]
                obj_base.min_layer = min(obj_base.min_layer, layer)
                continue
            c.layer = layer
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
            c.qualname = f"{c.qualname}_{layer}"
            c.name = f"{c.name}_{layer}"

    return schemas


def parse_old_objects(combinators_base: list[Combinator]) -> list[Combinator]:
    result = []
    for schema in parse_old_schemas(combinators_base).values():
        result.extend(schema.values())

    return result


def indent(lines: list[str], spaces: int) -> list[str]:
    return [" " * spaces + line for line in lines]


def get_real_type_from_type_and_subtype(type_name: str, subtype_name: str | None) -> str:
    if type_name in ("Int", "Long", "Int128", "Int256", "TLObject"):
        return type_name
    elif type_name == "bytes":
        return "Bytes"
    elif type_name == "str":
        return "String"
    elif type_name == "float":
        return "Float"
    elif type_name == "bool":
        return "Bool"
    elif type_name == "list":
        if not subtype_name:
            raise RuntimeError(f"Expected valid subtype name, got {subtype_name!r}")
        return f"{get_real_type_from_type_and_subtype(subtype_name, '')}Vector"
    else:
        raise RuntimeError(f"Got unknown type: {type_name=!r}, {subtype_name=!r}")


def resolve_fields_for_check(c: Combinator) -> list[Field]:
    if c.fields_for_check is not None:
        return c.fields_for_check

    c.fields_for_check = []

    if c.section != "types":
        return c.fields_for_check

    for field in c.fields:
        field_type = field.actual_type
        if field_type in CORE_TYPES:
            continue
        if field_type not in types_to_combinators:
            if field_type == "Object":
                c.fields_for_check.append(field)
            #else:
            #    print(field_type)
            continue

        has_fields_to_check = False

        for combinator in types_to_combinators[field_type]:
            has_fields_to_check = has_fields_to_check or bool(resolve_fields_for_check(combinator))

        if field_type in BASE_CLASSES_NEED_CONTEXT or has_fields_to_check:
            c.fields_for_check.append(field)

    return c.fields_for_check


def start():
    if not DRY_RUN:
        shutil.rmtree(DESTINATION_PATH / "base", ignore_errors=True)
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
        if c.section != "types":
            continue
        
        if c.qualtype.startswith("Vector"):
            raise RuntimeError(f"TL type constructors cannot be of type {c.qualtype}")

        types_to_constructors[c.qualtype].append(c.qualname)
        types_to_combinators[c.qualtype].append(c)
        if c.type not in namespaces_to_types[c.namespace]:
            namespaces_to_types[c.namespace].append(c.type)

    for c in tqdm(combinators, desc="Processing combinators", total=len(combinators)):
        c.fields = []
        flag_num = 1
        for arg in c.args:
            c.fields.append((field := Field(arg[0])))

            arg_type = arg[1]
            if arg_type == "#":
                field.flag_num = flag_num
                flag_num += 1
            if "?" in arg_type:
                bit = int(arg_type.split(".")[1].split("?")[0])
                this_flag_num = arg_type.split("?")[0].split(".")[0][5:]

                field.flag_bit = bit
                field.flag_num = int(this_flag_num) if this_flag_num else 1

                arg_type = arg_type.split("?", 1)[1]

            field.full_type = arg_type

    for c in tqdm(combinators, desc="Writing combinators"):
        slots = [f"\"{field.name}\"" for field in c.fields if not field.is_flag]
        slots.append("")  # For trailing comma

        init_args = [
            f"{field.name}: {get_type_hint(field.full_type, c.layer, True, True, force_optional=field.is_optional and field.type() != 'true')}"
            + ("" if not field.is_optional else (" = False" if field.type() in ("true", "Bool") else " = None"))
            for field in sorted(c.fields, key=lambda fd: (fd.is_optional, fd.position))
            if not field.is_flag
        ]
        if init_args:
            init_args.insert(0, "*")

        deserialize_cls_args = [
            f"{field.name}={field.name}"
            for field in c.fields if not field.is_flag
        ]

        placeholders = PLACEHOLDERS.get(int(c.id[2:], 16), {})

        fields_by_name = {
            field.name: field
            for field in c.fields
        }

        serialize_body = []
        deserialize_body = []

        fields_by_flag = defaultdict(list)
        for field in c.fields:
            if field.flag_num is None or field.flag_bit is None:
                continue
            fields_by_flag[(field.flag_num, field.flag_bit)].append(field.name)

        for same_flag_fields in fields_by_flag.values():
            if len(same_flag_fields) < 2:
                continue
            fields_empty = [
                (
                    f"self.{field_name} is False" if fields_by_name[field_name].type() == "true"
                    else f"self.{field_name} is None"
                )
                for field_name in same_flag_fields
            ]
            fields_not_empty = [
                (
                    f"self.{field_name} is True" if fields_by_name[field_name].type() == "true"
                    else f"self.{field_name} is not None"
                )
                for field_name in same_flag_fields
            ]
            serialize_body.append(f"_flags_fields_empty = ({', '.join(fields_empty)})")
            serialize_body.append(f"_flags_fields_not_empty = ({', '.join(fields_not_empty)})")
            serialize_body.append(f"if not (all(_flags_fields_empty) or all(_flags_fields_not_empty)):")
            serialize_body.append(
                f"    raise ValueError("
                f"\"Some of the optional fields are empty and some are not empty: {', '.join(same_flag_fields)}\""
                f")"
            )

        for field in c.fields:
            tmp_ = field.type().split("Vector<")

            subtype_name = None
            if field.is_vector:
                type_name_ = "list"
                tmp_ = tmp_[1].split(">")[0]
                if is_tl_object(tmp_):
                    subtype_name = "TLObject"
                else:
                    subtype_name = get_type_hint(tmp_, c.layer)
            else:
                tmp_ = tmp_[0]
                if is_tl_object(field.type()):
                    type_name_ = "TLObject"
                else:
                    type_name_ = get_type_hint(tmp_, c.layer)

            type_name = get_real_type_from_type_and_subtype(type_name_, subtype_name)
            if type_name == "TLObject" and len(types_to_constructors[field.type()]) == 1:
                type_name = f"tl.types.{types_to_constructors[field.type()][0]}"

            if field.is_flag:
                flag_var = f"flags{field.flag_num}"
                serialize_body.append(f"{flag_var} = 0")
                for ffield in c.fields:
                    if not ffield.is_optional or ffield.flag_num != field.flag_num:
                        continue
                    empty_condition = "" if ffield.type().lower().startswith("vector") or not ffield.write else " is not None"
                    serialize_body.append(f"if self.{ffield.name}{empty_condition}: {flag_var} |= (1 << {ffield.flag_bit})")
                serialize_body.append(f"result += Int.write({flag_var})")

                deserialize_body.append(f"{flag_var} = Int.read(stream)")
                continue

            write_var_name = f"self.{field.name}"
            if field.name in placeholders:
                name_with_ns = snake(c.qualname.replace(".", "_"))
                write_var_name = f"__{field.name}"
                for idx, (check, suffix) in enumerate(placeholders[field.name].items()):
                    if not idx:
                        serialize_body.append(f"if {check}:")
                    else:
                        serialize_body.append(f"elif {check}:")
                    serialize_body.append(
                        f"    {write_var_name} = tl_placeholders.{name_with_ns}_fill_{field.name}{suffix}(self, ctx)"
                    )
                serialize_body.append(f"else:")
                serialize_body.append(f"    {write_var_name} = self.{field.name}")

            if field.is_optional:
                if field.write:
                    empty_condition = ""
                    fields_with_this_flag = len([
                        1 for f in c.fields if f.flag_num == field.flag_num and f.flag_bit == field.flag_bit
                    ])
                    if fields_with_this_flag > 1 or not field.is_vector:
                        empty_condition = " is not None"

                    serialize_body.append(f"if {write_var_name}{empty_condition}:")
                    if type_name == "TLObject":
                        serialize_body.append(f"    result += {write_var_name}.write(ctx)")
                    else:
                        ctx_arg_maybe = ""
                        if type_name == "TLObjectVector":
                            ctx_arg_maybe = ", ctx"
                        serialize_body.append(f"    result += {type_name}.write({write_var_name}{ctx_arg_maybe})")
                    deserialize_body.append(
                        f"{field.name} = {type_name}.read(stream) "
                        f"if (flags{field.flag_num} & (1 << {field.flag_bit})) == (1 << {field.flag_bit}) else None"
                    )
                elif field.type() == "true":
                    deserialize_body.append(
                        f"{field.name} = (flags{field.flag_num} & (1 << {field.flag_bit})) == (1 << {field.flag_bit})"
                    )

                continue

            if type_name == "TLObject":
                serialize_body.append(f"result += {write_var_name}.write(ctx)")
            else:
                ctx_arg_maybe = ""
                if type_name == "TLObjectVector":
                    ctx_arg_maybe = ", ctx"
                serialize_body.append(f"result += {type_name}.write({write_var_name}{ctx_arg_maybe})")
            deserialize_body.append(f"{field.name} = {type_name}.read(stream)")

        to_check_body = []
        if c.section == "types":
            for field in resolve_fields_for_check(c):
                spaces = ""
                if field.is_optional:
                    to_check_body.append(f"if self.{field.name}:")
                    spaces = " " * 4

                if field.is_vector:
                    to_check_body.append(f"{spaces}for {field.name}_item in self.{field.name}:")
                    to_check_body.append(f"{spaces}    {field.name}_item.check_for_ctx_values(values)")
                else:
                    to_check_body.append(f"{spaces}self.{field.name}.check_for_ctx_values(values)")

        imports = [
            f"from __future__ import annotations",
            f"import bisect",
            f"from io import BytesIO",
            f"from ..primitives import *",
            f"from piltover import tl",
            f"from ..tl_object import TLObject",
            f"from ..serialization_context import SerializationContext, EMPTY_SERIALIZATION_CONTEXT",
        ]

        if c.section == "types":
            imports.append(f"from .. import placeholders as tl_placeholders")
            imports.append(f"from ..layer_info import layer as tl_base_layer")

        imports.append(f"")

        if c.section == "types":
            imports.extend((
                "from typing import TYPE_CHECKING",
                "if TYPE_CHECKING:",
                "    from piltover.context import NeedContextValuesContext",
                ""
            ))

        base_cls = "TLObject"
        if c.section == "functions":
            imports.append(f"from ..tl_object import TLRequest")
            if not c.typespace and c.type == "X":
                result_type = "TLObject"
            else:
                result_type = get_type_hint(f"{c.typespace}.{c.type}" if c.typespace else c.type, -1, True, True)
            base_cls = f"TLRequest[{result_type}]"

        result = [
            f"",
            f"",
            f"class {c.name}({base_cls}):",
            f"    __tl_id__ = {c.id}",
            f"    __tl_name__ = \"{c.section}.{c.qualname}\"",
            f"    __tl_layer__ = {c.layer if c.layer else c.min_layer}",
            f"",
            f"    __slots__ = ({', '.join(slots)})",
            *(
                [
                    f"",
                    f"    def __init__(self, {', '.join(init_args)}):",
                    *[
                        f"        self.{field.name} = {field.name}"
                        for field in c.fields if not field.is_flag
                    ],
                ] if init_args else []
            ),
            f"",
            f"    def serialize(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:",
            *indent(
                [
                    f"result = b\"\"",
                    *serialize_body,
                    f"return result",
                ] if serialize_body else [
                    "return b\"\""
                ],
                8
            ),
            f"",
            f"    @classmethod",
            f"    def deserialize(cls, stream: BytesIO) -> {c.name}:",
            *indent(deserialize_body, 8),
            f"        return cls({', '.join(deserialize_cls_args)})",
            *(
                [
                    f"",
                    f"    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:",
                    *indent(to_check_body, 8),
                ] if to_check_body else []
            ),
            f"",
        ]

        file_name = f"{c.namespace}.py" if c.namespace else "_root.py"
        out_path = DESTINATION_PATH / c.section / file_name
        if not DRY_RUN:
            out_path.parent.mkdir(parents=True, exist_ok=True)

        if not out_path.exists():
            with open(out_path, "w") as f:
                f.write("# mypy: disable-error-code=arg-type\n\n")
                f.write("\n".join(imports))
        with open(out_path, "a") as f:
            f.write("\n".join(result))

        d = namespaces_to_constructors if c.section == "types" else namespaces_to_functions
        d[c.namespace].append(c.name)

    combinator_by_qualname = defaultdict(list)
    for combinator in combinators:
        if combinator.section != "types":
            continue
        qualname = combinator.qualname
        if combinator.layer > 0 and qualname.endswith(str(combinator.layer)):
            qualname, *_ = qualname.rpartition("_")
        combinator_by_qualname[qualname].append(combinator)

    combinator_by_qualname = {k: v for k, v in combinator_by_qualname.items() if len(v) > 1}
    for older_combinators in tqdm(combinator_by_qualname.values(), desc="Writing downgradable combinators", total=len(combinator_by_qualname)):
        older_combinators.sort(key=lambda c_: (c_.layer or layer))
        oldest = older_combinators[0]
        base = older_combinators[-1]

        all_fields = []

        for field in oldest.fields:
            all_fields.append(Field(
                name=field.name,
                flag_bit=field.flag_bit,
                flag_num=field.flag_num,
                type_=field.full_type,
                min_layer=oldest.layer,
                max_layer=oldest.layer,
            ))

        for combinator in older_combinators[1:]:
            i = j = 0
            while i < len(all_fields) and j < len(combinator.fields):
                base_field = all_fields[i]
                new_field = combinator.fields[j]
                if base_field.name == new_field.name:
                    while i + 1 < len(all_fields) and all_fields[i + 1].name == new_field.name:
                        i += 1
                        base_field = all_fields[i]

                    if base_field == new_field:
                        base_field.max_layer = combinator.layer or layer
                        j += 1
                    i += 1
                else:
                    if i > 0 and all_fields[i - 1].name == new_field.name:
                        all_fields[i - 1].max_layer = combinator.min_layer
                    all_fields.insert(i, Field(
                        name=new_field.name,
                        flag_bit=new_field.flag_bit,
                        flag_num=new_field.flag_num,
                        type_=new_field.full_type,
                        min_layer=combinator.min_layer,
                        max_layer=combinator.layer or layer,
                    ))
                    i += 1
                    j += 1

            for i_ in range(i, len(all_fields)):
                all_fields[i_].max_layer = combinator.min_layer
            for j_ in range(j, len(combinator.fields)):
                new_field = combinator.fields[j_]
                all_fields.insert(i, Field(
                    name=new_field.name,
                    flag_bit=new_field.flag_bit,
                    flag_num=new_field.flag_num,
                    type_=new_field.full_type,
                    min_layer=combinator.min_layer,
                    max_layer=combinator.layer or layer,
                ))

        placeholders = PLACEHOLDERS.get(int(base.id[2:], 16), {})

        serialize_body = []

        base_fields = {field.name: field for field in base.fields}
        base_name_snake = snake(base.qualname.replace(".", "_"))

        # TODO: flags checking
        """
        fields_by_name = {
            field.name: field
            for field in c.fields
        }
        
        fields_by_flag = defaultdict(list)
        for field in c.fields:
            if field.flag_num is None or field.flag_bit is None:
                continue
            fields_by_flag[(field.flag_num, field.flag_bit)].append(field.name)

        for same_flag_fields in fields_by_flag.values():
            if len(same_flag_fields) < 2:
                continue
            fields_empty = [
                (
                    f"self.{field_name} is False" if fields_by_name[field_name].type() == "true"
                    else f"self.{field_name} is None"
                )
                for field_name in same_flag_fields
            ]
            fields_not_empty = [
                (
                    f"self.{field_name} is True" if fields_by_name[field_name].type() == "true"
                    else f"self.{field_name} is not None"
                )
                for field_name in same_flag_fields
            ]
            serialize_body.append(f"_flags_fields_empty = ({', '.join(fields_empty)})")
            serialize_body.append(f"_flags_fields_not_empty = ({', '.join(fields_not_empty)})")
            serialize_body.append(f"if not (all(_flags_fields_empty) or all(_flags_fields_not_empty)):")
            serialize_body.append(
                f"    raise ValueError("
                f"\"Some of the optional fields are empty and some are not empty: {', '.join(same_flag_fields)}\""
                f")"
            )
        """

        nonexistent_fields: dict[str, Field] = {}
        fields_to_downgrade: dict[str, Field] = {}

        field_var_names = []
        for field in all_fields:
            if field.name not in base_fields:
                assert not field.is_flag
                name = f"_{field.name}_fallback_{field.min_layer}"
                field_var_names.append(name)
                nonexistent_fields[name] = field
            elif field != base_fields[field.name]:
                assert not field.is_flag
                name = f"_{field.name}_downgrade_{field.min_layer}"
                field_var_names.append(name)
                fields_to_downgrade[name] = field
            else:
                field_var_names.append(f"self.{field.name}")

        for field, field_var_name in zip(all_fields, field_var_names):
            tmp_ = field.type().split("Vector<")

            subtype_name = None
            if field.is_vector:
                type_name_ = "list"
                tmp_ = tmp_[1].split(">")[0]
                if is_tl_object(tmp_):
                    subtype_name = "TLObject"
                else:
                    subtype_name = get_type_hint(tmp_, base.layer)
            else:
                tmp_ = tmp_[0]
                if is_tl_object(field.type()):
                    type_name_ = "TLObject"
                else:
                    type_name_ = get_type_hint(tmp_, base.layer)

            type_name = get_real_type_from_type_and_subtype(type_name_, subtype_name)
            if type_name == "TLObject" and len(types_to_constructors[field.type()]) == 1:
                type_name = f"tl.types.{types_to_constructors[field.type()][0]}"

            add_indent = ""
            if field.write:
                has_min_layer = field.min_layer > older_combinators[0].min_layer
                has_max_layer = field.max_layer < (older_combinators[-1].layer or layer)

                add_indent = " " * 4
                if has_min_layer and has_max_layer:
                    serialize_body.append(f"if {field.min_layer} <= ctx.layer < {field.max_layer}:")
                elif has_min_layer:
                    serialize_body.append(f"if ctx.layer >= {field.min_layer}:")
                elif has_max_layer:
                    serialize_body.append(f"if ctx.layer < {field.max_layer}:")
                else:
                    add_indent = ""

            if field.is_flag:
                flag_var = f"flags{field.flag_num}"
                serialize_body.append(f"{add_indent}{flag_var} = 0")
                for ffield, ffield_var_name in zip(all_fields, field_var_names):
                    if not ffield.is_optional or ffield.flag_num != field.flag_num \
                            or ffield.min_layer < field.min_layer or ffield.min_layer > field.max_layer:
                        continue
                    empty_condition = "" if ffield.type().lower().startswith("vector") or not ffield.write else " is not None"

                    ffield_has_min_layer = ffield.min_layer > older_combinators[0].min_layer
                    ffield_has_max_layer = ffield.max_layer < (older_combinators[-1].layer or layer)

                    ffield_add_indent = " " * 4
                    if ffield_has_min_layer and ffield_has_max_layer:
                        serialize_body.append(f"{add_indent}if {ffield.min_layer} <= ctx.layer < {ffield.max_layer}:")
                    elif ffield_has_min_layer:
                        serialize_body.append(f"{add_indent}if ctx.layer >= {ffield.min_layer}:")
                    elif ffield_has_max_layer:
                        serialize_body.append(f"{add_indent}if ctx.layer < {ffield.max_layer}:")
                    else:
                        ffield_add_indent = ""

                    serialize_body.append(f"{add_indent}{ffield_add_indent}if {ffield_var_name}{empty_condition}: {flag_var} |= (1 << {ffield.flag_bit})")
                serialize_body.append(f"{add_indent}result += Int.write({flag_var})")
                continue

            if field.name in placeholders:
                field_var_name_old = field_var_name
                field_var_name = f"_{field.name}_replaced"
                for idx, (check, suffix) in enumerate(placeholders[field.name].items()):
                    if not idx:
                        serialize_body.append(f"{add_indent}if {check}:")
                    else:
                        serialize_body.append(f"{add_indent}elif {check}:")
                    serialize_body.append(
                        f"    {add_indent}{field_var_name} = tl_placeholders.{base_name_snake}_fill_{field.name}{suffix}(self, ctx)"
                    )
                serialize_body.append(f"{add_indent}else:")
                serialize_body.append(f"    {add_indent}{field_var_name} = {field_var_name_old}")

            if field.is_optional:
                if field.write:
                    empty_condition = ""
                    fields_with_this_flag = len([
                        1 for f in all_fields if f.flag_num == field.flag_num and f.flag_bit == field.flag_bit
                    ])
                    if fields_with_this_flag > 1 or not field.is_vector:
                        empty_condition = " is not None"

                    serialize_body.append(f"{add_indent}if {field_var_name}{empty_condition}:")
                    if type_name == "TLObject":
                        serialize_body.append(f"    {add_indent}result += {field_var_name}.write(ctx)")
                    else:
                        ctx_arg_maybe = ""
                        if type_name == "TLObjectVector":
                            ctx_arg_maybe = ", ctx"
                        serialize_body.append(f"    {add_indent}result += {type_name}.write({field_var_name}{ctx_arg_maybe})")

                continue

            if type_name == "TLObject":
                serialize_body.append(f"{add_indent}result += {field_var_name}.write(ctx)")
            else:
                ctx_arg_maybe = ""
                if type_name == "TLObjectVector":
                    ctx_arg_maybe = ", ctx"
                serialize_body.append(f"{add_indent}result += {type_name}.write({field_var_name}{ctx_arg_maybe})")

        downgradable_cls_name = f"_{base.name}Downgradable"

        result = [
            f"",
            f"",
            f"class {downgradable_cls_name}({base.name}):",
            f"    __tl_ids__ = (",
            *indent(
                [
                    f"({c_.name}.__tl_layer__, {c_.name}.__tl_id__),"
                    for c_ in older_combinators
                ],
                spaces=8,
            ),
            f"    )",
            f"",
            f"    __slots__ = ()",
            f"",
            f"    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:",
            f"        if ctx.layer >= self.__tl_layer__:",
            f"            return super().write(ctx)",
            # TODO: add converter hooks
            #  e.g. something like placeholders that checks layer and then completely replaces current .write with custom one
            #  for example InvitedUsers may have ("177" and "convert_invited_users_to_updates" are customizable values here):
            #  ... if ctx.layer < 177:
            #  ...     return tl.layer_converters.invited_users.convert_invited_users_to_updates(self, ctx)
            #  and then tl.layer_converters.invited_users.convert_invited_users_to_updates is like this:
            #  ... def convert_invited_users_to_updates(obj: InvitedUsers, ctx: SerializationContext) -> bytes:
            #  ...     return obj.updates.write()
            f"",
            f"        if ctx.layer < self.__tl_ids__[0][0]:",
            f"            raise RuntimeError(",
            f"                f\"Client wants layer {{ctx.layer}} for object {{self.__class__.__name__!r}}, \"",
            f"                f\"but minimum available is {{self.__tl_ids__[0][0]}}\"",
            f"            )",
            f"",
            f"        layer_idx = bisect.bisect_left(self.__tl_ids__, ctx.layer, key=lambda e: e[0])",
            f"",
            *indent(
                [
                    f"{field_name} = tl.layer_converters.{base_name_snake}.get_{field.name}_fallback_for_{field.min_layer}(self, ctx)"
                    for field_name, field in nonexistent_fields.items()
                ] + ([""] if nonexistent_fields else []),
                spaces=8
            ),
            *indent(
                [
                    f"{field_name} = tl.layer_converters.{base_name_snake}.downgrade_{field.name}_for_{field.min_layer}(self, ctx)"
                    for field_name, field in fields_to_downgrade.items()
                ] + ([""] if fields_to_downgrade else []),
                spaces=8
            ),
            f"        result = Int.write(self.__tl_ids__[layer_idx][1], False)",
            *indent(
                [
                    *serialize_body,
                    f"return result",
                ] if serialize_body else [
                    "return b\"\""
                ],
                8
            ),
            f"",
        ]

        submodule_name = base.namespace if base.namespace else "_root"
        with open(DESTINATION_PATH / base.section / f"{submodule_name}.py", "a") as f:
            f.write("\n".join(result))

        converter_path = DESTINATION_PATH / "layer_converters" / f"{base_name_snake}.py"
        if (nonexistent_fields or fields_to_downgrade) and not converter_path.exists():
            with open(converter_path, "a") as f:
                cls_name_type = f"tl.types.{submodule_name}.{downgradable_cls_name}"

                f.write("from __future__ import annotations\n")
                f.write("from typing import TYPE_CHECKING\n")
                f.write("if TYPE_CHECKING:\n")
                f.write(f"    from piltover import tl\n")
                f.write(f"    from piltover.tl.serialization_context import SerializationContext\n")

                for field in nonexistent_fields.values():
                    f.write("\n\n")

                    field_type = get_type_hint(
                        field.full_type, field.min_layer, True, True,
                        force_optional=field.is_optional and field.type() != "true",
                    )

                    f.write(f"def get_{field.name}_fallback_for_{field.min_layer}(obj: {cls_name_type}, ctx: SerializationContext) -> {field_type}:\n")
                    f.write(f"    # TODO: Layer converter implementation of field \"{field.name}\" fallback will go here\n")
                    f.write(f"    # Note that field type is {field.tl_type}\n")
                    f.write(f"    raise NotImplementedError\n")

                for field in fields_to_downgrade.values():
                    f.write("\n\n")

                    base_field = base_fields[field.name]
                    field_type = get_type_hint(
                        field.full_type, field.min_layer, True, True,
                        force_optional=field.is_optional and field.type() != "true",
                    )

                    f.write(f"def downgrade_{field.name}_for_{field.min_layer}(obj: {cls_name_type}, ctx: SerializationContext) -> {field_type}:\n")
                    f.write(f"    # TODO: Layer converter implementation of field \"{field.name}\" downgrade will go here\n")
                    f.write(f"    # Note that field type needs to be {field.tl_type}, but now it's {base_field.tl_type}\n")
                    if base_field.full_type == "TextWithEntities" and field.full_type == "string":
                        f.write(f"    # Autogenerated\n")
                        f.write(f"    return obj.{field.name}.text\n")
                    elif base_field.full_type == field.full_type:
                        if base_field.is_optional and not field.is_optional:
                            f.write(f"    # Autogenerated\n")
                            f.write(f"    if obj.{field.name} is not None:\n")
                            f.write(f"        return obj.{field.name}\n")
                            if field.is_vector:
                                f.write(f"    return []\n")
                            elif field.full_type == "string":
                                f.write(f"    return \"\"\n")
                            else:
                                f.write(f"    # TODO: return fallback value\n")
                                f.write(f"    raise NotImplementedError\n")
                        elif field.is_optional and not base_field.is_optional:
                            f.write(f"    # Autogenerated\n")
                            f.write(f"    return obj.{field.name}\n")
                        else:
                            f.write(f"    raise NotImplementedError\n")
                    else:
                        f.write(f"    raise NotImplementedError\n")

    for namespace, types in namespaces_to_types.items():
        file_name = f"{namespace}.py" if namespace else "_root.py"
        base_file = DESTINATION_PATH / "base" / file_name
        if not DRY_RUN:
            base_file.parent.mkdir(parents=True, exist_ok=True)

        with open(base_file, "w") as f:
            f.write(f"{WARNING}\n\n")
            f.write("from piltover import tl\n\n")

            f.write("\n")

            if not namespace:
                f.write("FutureSalts = tl.core_types.FutureSalts\n")
                f.write("FutureSaltsInst = (tl.core_types.FutureSalts,)\n")
                f.write("\n")

            for t in types:
                qualtype = f"{namespace}.{t}" if namespace else t
                constructors = sorted(types_to_constructors[qualtype])

                types_pipe = " | ".join([f"tl.types.{c}" for c in constructors])
                f.write(f"{t} = {types_pipe}\n")

                # For isinstance() check
                types_comma = ", ".join([f"tl.types.{c}" for c in constructors])
                f.write(f"{t}Inst = ({types_comma},)\n")

                f.write("\n")

    with open(DESTINATION_PATH / "types" / "__init__.py", "a") as f:
        f.write(f"from ._root import *\n")
        f.write(f"from . import {', '.join(filter(bool, namespaces_to_constructors))}\n")

    with open(DESTINATION_PATH / "functions" / "__init__.py", "a") as f:
        f.write(f"from ._root import *\n")
        f.write(f"from . import {', '.join(filter(bool, namespaces_to_functions))}\n")

    with open(DESTINATION_PATH / "base" / "__init__.py", "a") as f:
        f.write(f"from ._root import *\n")
        f.write(f"from . import {', '.join(filter(bool, namespaces_to_types))}\n")

    with open(DESTINATION_PATH / "all.py", "w") as f:
        f.write(WARNING + "\n\n")
        f.write(f"from . import core_types, primitives, types, functions, to_format\n")
        f.write(f"# noinspection PyUnresolvedReferences\n")
        f.write(f"from .layer_info import min_layer, layer\n\n")
        f.write("objects = {\n")

        for c in combinators:
            id_int = int(c.id[2:], 16)
            if id_int in REPLACE_CONSTRUCTORS:
                f.write(f"    {c.id}: {REPLACE_CONSTRUCTORS[id_int]},\n")
            else:
                f.write(f"    {c.id}: {c.section}.{c.qualname},\n")

        f.write(f"    0x5bb8e511: core_types.Message,\n")
        f.write(f"    0x73f1f8dc: core_types.MsgContainer,\n")
        f.write(f"    0xf35c6d01: core_types.RpcResult,\n")
        f.write(f"    0x3072cfa1: core_types.GzipPacked,\n")
        f.write(f"    0xae500895: core_types.FutureSalts,\n")
        f.write(f"    0x997275b5: primitives.BoolTrue,\n")
        f.write(f"    0xbc799737: primitives.BoolFalse,\n")
        # TODO: vectors

        f.write("}\n")

    with open(DESTINATION_PATH / "layer_info.py", "w") as f:
        f.write(WARNING + "\n\n")
        f.write(f"min_layer = {min(all_layers)}\n")
        f.write(f"layer = {layer}\n\n")


if "__main__" == __name__:
    start()
