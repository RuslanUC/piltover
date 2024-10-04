import sys
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from shutil import copy

from tqdm import tqdm

EXCLUDE_VARS = {
    "Int", "Int128", "Int256", "Long", "Optional", "TLField", "TLObject", "Union", "Vector", "annotations",
    "classinstancemethod", "int_", "tl_object", "types", "vector",
}
TOOLS_DIR = Path(__file__).parent
SRC = Path(TOOLS_DIR.parent / "piltover")
SRC_TL = SRC / "tl_new"
DST_TL = SRC / "tl_new_c"


def type_annotation(field, opt_ack: bool = False, type_ack: bool = False) -> str:
    if field.flag != -1 and not opt_ack:
        if field.type.type is not bool or field.flag_serializable:
            return f"Optional[{type_annotation(field, True, type_ack)}]"
        return type_annotation(field, True, type_ack)
    if field.type.type is list and not type_ack:
        return f"list[{type_annotation(field, opt_ack, True)}]"
    t = field.type.type if not type_ack else field.type.subtype
    if t is None:
        return "None"

    if issubclass(t, int) and not issubclass(t, bool):
        return "int"

    return "TLObject" if hasattr(t, "__tl_id__") else t.__name__


def indent(lines: list[str], spaces: int) -> list[str]:
    return [" " * spaces + line for line in lines]


def main() -> None:
    piltover_spec = spec_from_file_location("piltover", SRC / "__init__.py")
    sys.modules["piltover"] = module_from_spec(piltover_spec)
    piltover_spec.loader.exec_module(sys.modules["piltover"])

    spec = spec_from_file_location("piltover.tl_new", SRC_TL / "__init__.py")
    tl_new = module_from_spec(spec)
    sys.modules["piltover.tl_new"] = tl_new
    spec.loader.exec_module(tl_new)

    for name, mod in tqdm(sys.modules.items(), desc="Processing classes"):
        if not name.startswith("piltover.tl_new.types") and not name.startswith("piltover.tl_new.functions"):
            continue
        if mod.__file__.endswith("__init__.py"):
            out_file = DST_TL / Path(mod.__file__).relative_to(SRC_TL)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            copy(mod.__file__, out_file)
            continue

        vars_ = list(set([var for var in dir(mod) if not var.startswith("__")]) - EXCLUDE_VARS)
        #assert len(vars_) == 1
        if len(vars_) != 1:
            continue
        class_name = vars_[0]
        class_ = getattr(mod, class_name)

        fields = [field.name for field in class_.__tl_fields__ if not field.is_flags]
        slots = [f"\"{slot}\"" for slot in fields]

        init_args = [
            f"{field.name}: {type_annotation(field)}"
            for field in sorted(class_.__tl_fields__, key=lambda fd: (fd.flag != -1, fd._counter))
            if not field.is_flags
        ]
        if init_args:
            init_args.insert(0, "*")

        deserialize_cls_args = [
            f"{field.name}={field.name}"
            for field in class_.__tl_fields__ if not field.is_flags
        ]

        third_dot = "." if class_.__tl_name__.count(".") > 1 else ""

        serialize_body = []
        deserialize_body = []
        for field in class_.__tl_fields__:
            int_subtype = field.type.subtype if field.type.subtype is not None and issubclass(field.type.subtype, int) \
                else None
            int_type = field.type.type if field.type.type is not None and issubclass(field.type.type, int) \
                else None
            int_type_name = int_subtype or int_type
            int_type_name = f", {int_type_name.__name__}" if int_type_name else ""

            type_name = field.type.type.__name__
            if hasattr(field.type.type, "__tl_id__"):
                type_name = "TLObject"

            subtype = field.type.subtype
            subtype_name = subtype.__name__ if subtype else None
            subtype_name = f", {'TLObject' if hasattr(subtype, '__tl_id__') else subtype_name}" if subtype else ""

            if field.is_flags:
                flag_var = f"flags{field.flagnum}"
                serialize_body.append(f"{flag_var} = 0")
                for ffield in class_.__tl_fields__:
                    if ffield.flag == -1 or ffield.flagnum != field.flagnum:
                        continue
                    serialize_body.append(f"if self.{ffield.name}: {flag_var} |= {ffield.flag}")
                serialize_body.append(f"result += SerializationUtils.write({flag_var}, Int)")

                deserialize_body.append(f"{flag_var} = SerializationUtils.read(stream, Int)")
                continue

            if field.flag != -1:
                if field.type.type is not bool or field.flag_serializable:
                    serialize_body.append(f"if self.{field.name}:")
                    serialize_body.append(f"    SerializationUtils.write(self.{field.name}{int_type_name})")
                    #deserialize_body.append(f"if (flags{field.flagnum} & {field.flag}) == {field.flag}:")
                    deserialize_body.append(
                        f"{field.name} = SerializationUtils.read(stream, {type_name}{subtype_name}) "
                        f"if (flags{field.flagnum} & {field.flag}) == {field.flag} else None"
                    )
                elif field.type.type is bool:
                    deserialize_body.append(f"{field.name} = (flags{field.flagnum} & {field.flag}) == {field.flag}")

                continue

            serialize_body.append(f"result += SerializationUtils.write(self.{field.name}{int_type_name})")
            deserialize_body.append(f"{field.name} = SerializationUtils.read(stream, {type_name}{subtype_name})")

        result = [
            f"from typing import Optional",
            f"from {third_dot}..primitives import *",
            f"from {third_dot}.. import types, SerializationUtils",
            f"from {third_dot}..tl_object import TLObject",
            f"",
            f"",
            f"class {class_name}(TLObject):",
            f"    __tl_id__ = {hex(class_.__tl_id__)}",
            f"    __tl_name__ = \"{class_.__tl_name__}\"",
            f"",
            f"    __slots__ = ({', '.join(slots)})",
            f"",
            f"    def __init__(self, {', '.join(init_args)}):",
            f"        ...",
            *[
                f"        self.{field_name} = {field_name}"
                for field_name in fields
            ],
            f"",
            f"    def serialize(self) -> bytes:",
            f"        result = b\"\"",
            *indent(serialize_body, 8),
            f"        return result",
            f"",
            f"    @classmethod",
            f"    def deserialize(cls, stream) -> TLObject:",
            *indent(deserialize_body, 8),
            f"        return cls({', '.join(deserialize_cls_args)})",
            f"",
        ]

        out_file = DST_TL / Path(mod.__file__).relative_to(SRC_TL)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            f.write("\n".join(result))


if __name__ == '__main__':
    main()
