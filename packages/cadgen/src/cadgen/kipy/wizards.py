# Copyright The KiCad Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import argparse
import json
import sys
from typing import Union

from google.protobuf.json_format import (
    MessageToJson,
    ParseDict,
    ParseError,
)

from cadgen.kipy.proto.common import types

# Re-exported protobuf enum types
from cadgen.kipy.proto.common.types.wizards_pb2 import (  # noqa: F401
    WizardContentType,
    WizardParameterCategory,
    WizardParameterDataType,
)
from cadgen.kipy.wrapper import Wrapper

WizardParameterValue = Union[int, float, bool, str]


class WizardError(Exception):
    """An error returned by a wizard during generation"""


class WizardMetaInfo(Wrapper):
    def __init__(
        self,
        proto: types.WizardMetaInfo | None = None,
        proto_ref: types.WizardMetaInfo | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardMetaInfo()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def identifier(self) -> str:
        return self._proto.identifier

    @identifier.setter
    def identifier(self, value: str):
        self._proto.identifier = value

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def description(self) -> str:
        return self._proto.description

    @description.setter
    def description(self, value: str):
        self._proto.description = value

    @property
    def types_generated(self) -> list[types.WizardContentType.ValueType]:
        return list(self._proto.types_generated)

    @types_generated.setter
    def types_generated(self, value: list[types.WizardContentType.ValueType]):
        del self._proto.types_generated[:]
        self._proto.types_generated.extend(value)


class WizardIntParameter(Wrapper):
    def __init__(
        self,
        proto: types.WizardIntParameter | None = None,
        proto_ref: types.WizardIntParameter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardIntParameter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def value(self) -> int:
        return self._proto.value

    @value.setter
    def value(self, value: int):
        self._proto.value = value

    @property
    def default(self) -> int:
        return self._proto.default

    @default.setter
    def default(self, value: int):
        self._proto.default = value

    @property
    def min(self) -> int | None:
        if self._proto.HasField("min"):
            return self._proto.min
        return None

    @min.setter
    def min(self, value: int | None):
        if value is None:
            self._proto.ClearField("min")
        else:
            self._proto.min = value

    @property
    def max(self) -> int | None:
        if self._proto.HasField("max"):
            return self._proto.max
        return None

    @max.setter
    def max(self, value: int | None):
        if value is None:
            self._proto.ClearField("max")
        else:
            self._proto.max = value

    @property
    def multiple(self) -> int | None:
        if self._proto.HasField("multiple"):
            return self._proto.multiple
        return None

    @multiple.setter
    def multiple(self, value: int | None):
        if value is None:
            self._proto.ClearField("multiple")
        else:
            self._proto.multiple = value


class WizardRealParameter(Wrapper):
    def __init__(
        self,
        proto: types.WizardRealParameter | None = None,
        proto_ref: types.WizardRealParameter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardRealParameter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def value(self) -> float:
        return self._proto.value

    @value.setter
    def value(self, value: float):
        self._proto.value = value

    @property
    def default(self) -> float:
        return self._proto.default

    @default.setter
    def default(self, value: float):
        self._proto.default = value

    @property
    def min(self) -> float | None:
        if self._proto.HasField("min"):
            return self._proto.min
        return None

    @min.setter
    def min(self, value: float | None):
        if value is None:
            self._proto.ClearField("min")
        else:
            self._proto.min = value

    @property
    def max(self) -> float | None:
        if self._proto.HasField("max"):
            return self._proto.max
        return None

    @max.setter
    def max(self, value: float | None):
        if value is None:
            self._proto.ClearField("max")
        else:
            self._proto.max = value


class WizardBoolParameter(Wrapper):
    def __init__(
        self,
        proto: types.WizardBoolParameter | None = None,
        proto_ref: types.WizardBoolParameter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardBoolParameter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def value(self) -> bool:
        return self._proto.value

    @value.setter
    def value(self, value: bool):
        self._proto.value = value

    @property
    def default(self) -> bool:
        return self._proto.default

    @default.setter
    def default(self, value: bool):
        self._proto.default = value


class WizardStringParameter(Wrapper):
    def __init__(
        self,
        proto: types.WizardStringParameter | None = None,
        proto_ref: types.WizardStringParameter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardStringParameter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def value(self) -> str:
        return self._proto.value

    @value.setter
    def value(self, value: str):
        self._proto.value = value

    @property
    def default(self) -> str:
        return self._proto.default

    @default.setter
    def default(self, value: str):
        self._proto.default = value

    @property
    def validation_regex(self) -> str | None:
        if self._proto.HasField("validation_regex"):
            return self._proto.validation_regex
        return None

    @validation_regex.setter
    def validation_regex(self, value: str | None):
        if value is None:
            self._proto.ClearField("validation_regex")
        else:
            self._proto.validation_regex = value


class WizardParameter(Wrapper):
    def __init__(
        self,
        proto: types.WizardParameter | None = None,
        proto_ref: types.WizardParameter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardParameter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @classmethod
    def create(
        cls,
        identifier: str,
        name: str,
        category: types.WizardParameterCategory.ValueType,
        data_type: types.WizardParameterDataType.ValueType,
        value: WizardParameterValue | None = None,
        description: str = "",
        default: WizardParameterValue | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        multiple: int | None = None,
        validation_regex: str | None = None,
    ) -> WizardParameter:
        param = cls()
        param.identifier = identifier
        param.name = name
        param.description = description
        param.category = category
        param.type = data_type

        if value is None:
            if data_type in (
                types.WizardParameterDataType.WPDT_DISTANCE,
                types.WizardParameterDataType.WPDT_AREA,
                types.WizardParameterDataType.WPDT_VOLUME,
                types.WizardParameterDataType.WPDT_TIME,
                types.WizardParameterDataType.WPDT_INTEGER,
            ):
                value = 0
            elif data_type in (
                types.WizardParameterDataType.WPDT_ANGLE,
                types.WizardParameterDataType.WPDT_REAL,
            ):
                value = 0.0
            elif data_type == types.WizardParameterDataType.WPDT_BOOL:
                value = False
            elif data_type == types.WizardParameterDataType.WPDT_STRING:
                value = ""

        if default is None:
            default = value

        assert value is not None
        assert default is not None

        if data_type in (
            types.WizardParameterDataType.WPDT_DISTANCE,
            types.WizardParameterDataType.WPDT_AREA,
            types.WizardParameterDataType.WPDT_VOLUME,
            types.WizardParameterDataType.WPDT_TIME,
            types.WizardParameterDataType.WPDT_INTEGER,
        ):
            param.int_value = int(value)
            param.int_default = int(default)
            param.int_min = int(min_value) if min_value is not None else None
            param.int_max = int(max_value) if max_value is not None else None
            param.int_multiple = multiple
        elif data_type in (
            types.WizardParameterDataType.WPDT_ANGLE,
            types.WizardParameterDataType.WPDT_REAL,
        ):
            param.real_value = float(value)
            param.real_default = float(default)
            param.real_min = float(min_value) if min_value is not None else None
            param.real_max = float(max_value) if max_value is not None else None
        elif data_type == types.WizardParameterDataType.WPDT_BOOL:
            param.bool_value = bool(value)
            param.bool_default = bool(default)
        elif data_type == types.WizardParameterDataType.WPDT_STRING:
            param.string_value = str(value)
            param.string_default = str(default)
            param.string_validation_regex = validation_regex
        else:
            raise ValueError(f"Unsupported WizardParameter data type: {data_type!r}")

        return param

    @property
    def identifier(self) -> str:
        return self._proto.identifier

    @identifier.setter
    def identifier(self, value: str):
        self._proto.identifier = value

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def description(self) -> str:
        return self._proto.description

    @description.setter
    def description(self, value: str):
        self._proto.description = value

    @property
    def category(self) -> types.WizardParameterCategory.ValueType:
        return self._proto.category

    @category.setter
    def category(self, value: types.WizardParameterCategory.ValueType):
        self._proto.category = value

    @property
    def type(self) -> types.WizardParameterDataType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: types.WizardParameterDataType.ValueType):
        self._proto.type = value

    def which_value(self) -> str | None:
        return self._proto.WhichOneof("value")

    def clear_value(self):
        which = self.which_value()
        if which == "int":
            self._proto.ClearField("int")
        elif which == "real":
            self._proto.ClearField("real")
        elif which == "bool":
            self._proto.ClearField("bool")
        elif which == "string":
            self._proto.ClearField("string")

    @property
    def value(self) -> WizardParameterValue | None:
        which = self.which_value()
        if which is None:
            return None
        if which == "int":
            return int(self._proto.int.value)
        if which == "real":
            return float(self._proto.real.value)
        if which == "bool":
            return bool(self._proto.bool.value)
        if which == "string":
            return str(self._proto.string.value)
        return None

    @value.setter
    def value(self, value: WizardParameterValue | None):
        if value is None:
            self.clear_value()
            return

        if self.type in (
            types.WizardParameterDataType.WPDT_DISTANCE,
            types.WizardParameterDataType.WPDT_AREA,
            types.WizardParameterDataType.WPDT_VOLUME,
            types.WizardParameterDataType.WPDT_TIME,
            types.WizardParameterDataType.WPDT_INTEGER,
        ):
            self.int_value = int(value)
        elif self.type in (
            types.WizardParameterDataType.WPDT_ANGLE,
            types.WizardParameterDataType.WPDT_REAL,
        ):
            self.real_value = float(value)
        elif self.type == types.WizardParameterDataType.WPDT_BOOL:
            self.bool_value = bool(value)
        elif self.type == types.WizardParameterDataType.WPDT_STRING:
            self.string_value = str(value)
        else:
            raise ValueError(f"Unsupported WizardParameter data type: {self.type!r}")

    @property
    def default_value(self) -> WizardParameterValue | None:
        which = self.which_value()
        if which is None:
            return None
        if which == "int":
            return int(self._proto.int.default)
        if which == "real":
            return float(self._proto.real.default)
        if which == "bool":
            return bool(self._proto.bool.default)
        if which == "string":
            return str(self._proto.string.default)
        return None

    @default_value.setter
    def default_value(self, value: WizardParameterValue | None):
        if value is None:
            return
        if self.type in (
            types.WizardParameterDataType.WPDT_DISTANCE,
            types.WizardParameterDataType.WPDT_AREA,
            types.WizardParameterDataType.WPDT_VOLUME,
            types.WizardParameterDataType.WPDT_TIME,
            types.WizardParameterDataType.WPDT_INTEGER,
        ):
            self.int_default = int(value)
        elif self.type in (
            types.WizardParameterDataType.WPDT_ANGLE,
            types.WizardParameterDataType.WPDT_REAL,
        ):
            self.real_default = float(value)
        elif self.type == types.WizardParameterDataType.WPDT_BOOL:
            self.bool_default = bool(value)
        elif self.type == types.WizardParameterDataType.WPDT_STRING:
            self.string_default = str(value)

    @property
    def int_param(self) -> WizardIntParameter:
        return WizardIntParameter(proto_ref=self._proto.int)

    @int_param.setter
    def int_param(self, value: WizardIntParameter):
        self._proto.int.CopyFrom(value.proto)

    @property
    def real_param(self) -> WizardRealParameter:
        return WizardRealParameter(proto_ref=self._proto.real)

    @real_param.setter
    def real_param(self, value: WizardRealParameter):
        self._proto.real.CopyFrom(value.proto)

    @property
    def bool_param(self) -> WizardBoolParameter:
        return WizardBoolParameter(proto_ref=self._proto.bool)

    @bool_param.setter
    def bool_param(self, value: WizardBoolParameter):
        self._proto.bool.CopyFrom(value.proto)

    @property
    def string_param(self) -> WizardStringParameter:
        return WizardStringParameter(proto_ref=self._proto.string)

    @string_param.setter
    def string_param(self, value: WizardStringParameter):
        self._proto.string.CopyFrom(value.proto)

    @property
    def int_value(self) -> int:
        return self._proto.int.value

    @int_value.setter
    def int_value(self, value: int):
        self._proto.int.value = value

    @property
    def int_default(self) -> int:
        return self._proto.int.default

    @int_default.setter
    def int_default(self, value: int):
        self._proto.int.default = value

    @property
    def int_min(self) -> int | None:
        if self._proto.int.HasField("min"):
            return self._proto.int.min
        return None

    @int_min.setter
    def int_min(self, value: int | None):
        if value is None:
            self._proto.int.ClearField("min")
        else:
            self._proto.int.min = value

    @property
    def int_max(self) -> int | None:
        if self._proto.int.HasField("max"):
            return self._proto.int.max
        return None

    @int_max.setter
    def int_max(self, value: int | None):
        if value is None:
            self._proto.int.ClearField("max")
        else:
            self._proto.int.max = value

    @property
    def int_multiple(self) -> int | None:
        if self._proto.int.HasField("multiple"):
            return self._proto.int.multiple
        return None

    @int_multiple.setter
    def int_multiple(self, value: int | None):
        if value is None:
            self._proto.int.ClearField("multiple")
        else:
            self._proto.int.multiple = value

    @property
    def real_value(self) -> float:
        return self._proto.real.value

    @real_value.setter
    def real_value(self, value: float):
        self._proto.real.value = value

    @property
    def real_default(self) -> float:
        return self._proto.real.default

    @real_default.setter
    def real_default(self, value: float):
        self._proto.real.default = value

    @property
    def real_min(self) -> float | None:
        if self._proto.real.HasField("min"):
            return self._proto.real.min
        return None

    @real_min.setter
    def real_min(self, value: float | None):
        if value is None:
            self._proto.real.ClearField("min")
        else:
            self._proto.real.min = value

    @property
    def real_max(self) -> float | None:
        if self._proto.real.HasField("max"):
            return self._proto.real.max
        return None

    @real_max.setter
    def real_max(self, value: float | None):
        if value is None:
            self._proto.real.ClearField("max")
        else:
            self._proto.real.max = value

    @property
    def bool_value(self) -> bool:
        return self._proto.bool.value

    @bool_value.setter
    def bool_value(self, value: bool):
        self._proto.bool.value = value

    @property
    def bool_default(self) -> bool:
        return self._proto.bool.default

    @bool_default.setter
    def bool_default(self, value: bool):
        self._proto.bool.default = value

    @property
    def string_value(self) -> str:
        return self._proto.string.value

    @string_value.setter
    def string_value(self, value: str):
        self._proto.string.value = value

    @property
    def string_default(self) -> str:
        return self._proto.string.default

    @string_default.setter
    def string_default(self, value: str):
        self._proto.string.default = value

    @property
    def string_validation_regex(self) -> str | None:
        if self._proto.string.HasField("validation_regex"):
            return self._proto.string.validation_regex
        return None

    @string_validation_regex.setter
    def string_validation_regex(self, value: str | None):
        if value is None:
            self._proto.string.ClearField("validation_regex")
        else:
            self._proto.string.validation_regex = value


class WizardInfo(Wrapper):
    def __init__(
        self,
        proto: types.WizardInfo | None = None,
        proto_ref: types.WizardInfo | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.WizardInfo()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._meta = WizardMetaInfo(proto_ref=self._proto.meta)
        self._parameters = [WizardParameter(proto_ref=p) for p in self._proto.parameters]

    def _pack(self):
        self._proto.meta.CopyFrom(self._meta.proto)
        del self._proto.parameters[:]
        self._proto.parameters.extend([p.proto for p in self._parameters])

    @property
    def meta(self) -> WizardMetaInfo:
        return WizardMetaInfo(proto_ref=self._proto.meta)

    @meta.setter
    def meta(self, value: WizardMetaInfo):
        self._proto.meta.CopyFrom(value.proto)
        self._meta = WizardMetaInfo(proto_ref=self._proto.meta)

    @property
    def parameters(self) -> list[WizardParameter]:
        return self._parameters

    @parameters.setter
    def parameters(self, value: list[WizardParameter]):
        self._parameters = value


class WizardBase:
    def __init__(self, description: str) -> None:
        self.description = description

    def build_wizard_info(self) -> WizardInfo:
        raise NotImplementedError("Implement build_wizard_info to describe your wizard")

    def build_generated_content(self, parameters: list[WizardParameter] | None = None) -> Wrapper:
        raise NotImplementedError(
            "Implement generate to generate content based on the provided parameters"
        )

    def run(self):
        args = self.parse_args(sys.argv[1:])
        proto = None

        if args.get_info:
            proto = self.build_wizard_info().proto
        elif args.generate:
            parameters, parse_error = self._load_generate_parameters(args)
            proto = self._generate(parameters, parse_error)

        if proto is not None:
            output_json = MessageToJson(
                proto,
                preserving_proto_field_name=True,
            )
            print(output_json)

    def parse_args(self, argv: list[str]):
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument(
            "--get-info",
            action="store_true",
            help="Called by KiCad to query the wizard's metadata and parameters",
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Called by KiCad to generate content based on the provided parameters",
        )
        parser.add_argument(
            "--params",
            type=str,
            help="A JSON-encoded WizardParameterList protobuf message (only used with --generate)",
        )
        parser.add_argument(
            "--lang",
            type=str,
            help="Optional language/locale hint (unused by this example)",
        )
        return parser.parse_args(argv)

    def _generate(
        self,
        parameters: list[WizardParameter] | None = None,
        parse_error: str | None = None,
    ) -> types.WizardGeneratedContent:
        generated = types.WizardGeneratedContent()

        if parse_error is not None:
            generated.status = types.WizardGenerationStatus.WGS_ERROR
            generated.error_message = parse_error
            return generated

        try:
            footprint = self.build_generated_content(parameters)
        except (WizardError, NotImplementedError, ValueError, TypeError) as ex:
            generated.status = types.WizardGenerationStatus.WGS_ERROR
            generated.error_message = f"Generation failed: {ex!s}"
            return generated

        generated.status = types.WizardGenerationStatus.WGS_OK
        generated.content.Pack(footprint.proto)
        return generated

    def _load_generate_parameters(
        self,
        args: argparse.Namespace,
    ) -> tuple[list[WizardParameter] | None, str | None]:
        if args.params is None:
            return None, None

        try:
            container = types.WizardParameterList()
            ParseDict(json.loads(args.params), container, ignore_unknown_fields=True)
        except ParseError as ex:
            return None, f"Invalid --params protobuf JSON: {ex!s}"
        except (ValueError, TypeError) as ex:
            return None, f"Invalid --params value: {ex!s}"

        return [WizardParameter(proto=proto_param) for proto_param in container.parameters], None
