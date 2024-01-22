from collections import defaultdict
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import NamedTuple

from tools.tl_gen import parse_old_schemas, parse_schema, Combinator, snake

# noinspection PyShadowingBuiltins
open = partial(open, encoding="utf-8")


class ArgsDifference(NamedTuple):
    name: str
    old_layer: int
    section: str
    added: set[tuple[str, str]]
    deleted: set[tuple[str, str]]
    updated: list[tuple[tuple[str, str], tuple[str, str]]]


def args_difference(qualname: str, combinator: Combinator, base: set[tuple[str, str]], old: set[tuple[str, str]]) -> ArgsDifference:
    added = base - old
    deleted = old - base
    updated = []

    added_names = {arg[0] for arg in added}
    deleted_names = {arg[0] for arg in deleted}
    for name in added_names & deleted_names:
        arg_new = [arg for arg in added if arg[0] == name][0]
        arg_old = [arg for arg in deleted if arg[0] == name][0]
        added.remove(arg_new)
        deleted.remove(arg_old)
        updated.append((arg_old, arg_new))

    return ArgsDifference(qualname, combinator.layer, combinator.section, added, deleted, updated)


def parse_differences(schemaBase: list[Combinator]) -> list[ArgsDifference]:
    schemas = parse_old_schemas(schemaBase)
    schemaBase = {f"{c.qualname}#{c.id}": c for c in schemaBase}

    differences = []
    for schema in schemas.values():
        for name, combinator in schema.items():
            name = name.split("#")[0]
            base_type = [base_name for base_name in schemaBase if base_name.startswith(name + "#")]
            if not base_type:
                continue
            base_type = schemaBase[base_type[0]]
            args_this = set(deepcopy(combinator.args))
            args_base = set(deepcopy(base_type.args))
            differences.append(args_difference(name, combinator, args_base, args_this))

    return differences


# noinspection PyShadowingBuiltins
def start():
    with open(HOME_PATH / "resources/mtproto.tl") as f1, open(HOME_PATH / "resources/api.tl") as f2:
        schema = f1.read().splitlines() + f2.read().splitlines()

    with open(HOME_PATH / "templates/converter.txt") as f:
        converter_tmpl = f.read()

    combinators, _ = parse_schema(schema)
    differences = parse_differences(combinators)

    differences_ = defaultdict(list)
    for difference in differences:
        differences_[difference.name].append(difference)

    del differences

    for base, diff in differences_.items():
        namespace = base.split(".")[0] if "." in base else ""
        base = base.split(".")[1] if "." in base else base
        file_name = f"{namespace}_{snake(base)}.py" if namespace else f"{snake(base)}.py"
        file_path = DESTINATION_PATH / "converter" / "converters" / file_name
        if file_path.exists():
            print(f"Converter for {base} already exists, skipping")
            continue

        layers = ", ".join([f"{d.old_layer}" for d in diff])
        old_ = [f"{base}_{d.old_layer}" for d in diff]
        objects = [base] + old_
        old_ = ", ".join(old_)
        objects = ", ".join(objects)
        methods = ""

        diff_layer: ArgsDifference
        for diff_layer in diff:
            layer = diff_layer.old_layer
            upgrade = ""
            downgrade = ""

            for field_name, field_type in diff_layer.added:
                downgrade += f"        del data[\"{field_name}\"]\n"
                if "?" in field_type or field_type == "#":
                    continue
                upgrade += f"        assert False, \"required field '{field_name}' added in base tl object\""
                upgrade += f"  # TODO: add field\n"

            for field_name, field_type in diff_layer.deleted:
                upgrade += f"        del data[\"{field_name}\"]\n"
                if "?" in field_type or field_type == "#":
                    continue
                downgrade += f"        assert False, \"required field '{field_name}' deleted in base tl object\""
                downgrade += f"  # TODO: delete field\n"

            for old, new in diff_layer.updated:
                upgrade += f"        assert False, \"type of field '{old[0]}' changed ({old[1]} -> {new[1]})\""
                upgrade += f"  # TODO: type changed\n"

                downgrade += f"        assert False, \"type of field '{old[0]}' changed ({new[1]} -> {old[1]})\""
                downgrade += f"  # TODO: type changed\n"

            methods += f"    @staticmethod\n"
            methods += f"    def from_{layer}(obj: {base}_{layer}) -> {base}:\n"
            methods += f"        data = obj.to_dict()\n{upgrade}"
            methods += f"        return {base}(**data)\n\n"

            methods += f"    @staticmethod\n"
            methods += f"    def to_{layer}(obj: {base}) -> {base}_{layer}:\n"
            methods += f"        data = obj.to_dict()\n{downgrade}"
            methods += f"        return {base}_{layer}(**data)\n\n"

        namespace_ = f".{diff[0].section}"
        if namespace:
            namespace_ += f".{namespace}"

        with open(file_path, "w") as f:
            f.write(converter_tmpl.format(
                base=base,
                old=old_,
                layers=layers,
                objects=objects,
                namespace=namespace_,
                methods=methods,
            ))


if "__main__" == __name__:
    HOME_PATH = Path("./tools")
    DESTINATION_PATH = Path("piltover/tl_new")

    start()
