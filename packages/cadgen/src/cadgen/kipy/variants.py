# Copyright The KiCad Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

from google.protobuf.empty_pb2 import Empty

from cadgen.kipy.client import KiCadClient
from cadgen.kipy.common_types import DesignVariant
from cadgen.kipy.proto.common.commands import variant_commands_pb2
from cadgen.kipy.proto.common.types import DocumentSpecifier


class VariantsCommandHandler:
    """Mixin class for working with design variants"""

    _kicad: KiCadClient
    _doc: DocumentSpecifier

    def get_variants(self) -> list[DesignVariant]:
        """Returns the document's variants, excluding the default variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.GetVariants()
        command.document.CopyFrom(self._doc)
        response = self._kicad.send(command, variant_commands_pb2.VariantsResponse)
        return [DesignVariant(proto=variant) for variant in response.variants]

    def add_variant(self, name: str, description: str | None = None) -> None:
        """Adds a variant to the document

        :param name: The name of the variant (must be case-insensitively unique)
        :param description: An optional description for the variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.AddVariant()
        command.document.CopyFrom(self._doc)
        command.name = name

        if description is not None:
            command.description = description

        self._kicad.send(command, Empty)

    def delete_variant(self, name: str) -> None:
        """Deletes a variant and all its per-item records

        Deleting the current variant resets the active variant to the default.

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.DeleteVariant()
        command.document.CopyFrom(self._doc)
        command.name = name
        self._kicad.send(command, Empty)

    def rename_variant(self, old_name: str, new_name: str) -> None:
        """Renames a variant

        :param old_name: The current name of the variant
        :param new_name: The new name for the variant; must be case-insensitively unique

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.RenameVariant()
        command.document.CopyFrom(self._doc)
        command.old_name = old_name
        command.new_name = new_name
        self._kicad.send(command, Empty)

    def set_variant_description(self, name: str, description: str) -> None:
        """Sets the description for a variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.SetVariantDescription()
        command.document.CopyFrom(self._doc)
        command.name = name
        command.description = description
        self._kicad.send(command, Empty)

    def copy_variant(
        self, old_name: str, new_name: str, new_description: str | None = None
    ) -> None:
        """Copies a variant to a new variant, including all item overrides

        :param old_name: The name of the variant to copy
        :param new_name: The name for the new variant; must be case-insensitively unique
        :param new_description: An optional description for the new variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.CopyVariant()
        command.document.CopyFrom(self._doc)
        command.old_name = old_name
        command.new_name = new_name

        if new_description is not None:
            command.new_description = new_description

        self._kicad.send(command, Empty)

    def get_current_variant(self) -> str | None:
        """Returns the name of the currently applied variant, or None for the default variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.GetCurrentVariant()
        command.document.CopyFrom(self._doc)
        response = self._kicad.send(command, variant_commands_pb2.CurrentVariantResponse)
        return response.name if response.HasField("name") else None

    def set_current_variant(self, name: str | None = None) -> None:
        """Selects the active variant in the editor

        :param name: The name of the variant to select, or None to select the default variant

        .. versionadded:: 0.9.0"""
        command = variant_commands_pb2.SetCurrentVariant()
        command.document.CopyFrom(self._doc)

        if name is not None:
            command.name = name

        self._kicad.send(command, Empty)
