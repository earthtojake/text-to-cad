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
# OUT OF OR IN connection WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Shared commands for document editors (board, schematic, etc)."""

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Sequence
from typing import Any, Generic, TypeVar

from google.protobuf.empty_pb2 import Empty

from cadgen.kipy.client import KiCadClient
from cadgen.kipy.common_types import Commit
from cadgen.kipy.proto.common.commands import editor_commands_pb2, project_commands_pb2
from cadgen.kipy.proto.common.types import KIID, DocumentSpecifier, KiCadObjectType
from cadgen.kipy.util import pack_any
from cadgen.kipy.wrapper import Item, Wrapper

_ItemT_co = TypeVar("_ItemT_co", bound=Item, covariant=True)


class EditorCommandsHandler(Generic[_ItemT_co]):
    """Mixin implementing the commands that KiCad handles identically for every
    open editor document.

    Subclasses must provide ``_kicad`` (a :class:`KiCadClient`), ``_doc`` (the
    :class:`DocumentSpecifier` of the open document), and ``_item_from_message``, which
    converts a generic unwrapped message into the document's concrete type.
    """

    _kicad: KiCadClient
    _doc: DocumentSpecifier

    def _item_from_message(self, message: Any) -> _ItemT_co:
        """Converts an unwrapped protobuf message into a concrete item wrapper"""
        raise NotImplementedError

    def save(self):
        command = project_commands_pb2.SaveDocument()
        command.document.CopyFrom(self._doc)
        self._kicad.send(command, Empty)

    def save_as(self, filename: str, overwrite: bool = False, include_project: bool = True):
        """
        Saves the document to a new file.  Does not open the newly-saved file.

        :param filename: The path to save the document to
        :param overwrite: If True, the file will be overwritten if it already exists
        :param include_project: If True, the project will be saved along with the document
        """
        path = pathlib.Path(filename)
        command = editor_commands_pb2.SaveCopyOfDocument()
        command.document.CopyFrom(self._doc)
        command.path = str(path.resolve())
        command.options.overwrite = overwrite
        command.options.include_project = include_project
        self._kicad.send(command, Empty)

    def revert(self):
        """Reverts the document to the last saved state"""
        command = editor_commands_pb2.RevertDocument()
        command.document.CopyFrom(self._doc)
        self._kicad.send(command, Empty)

    def begin_commit(self) -> Commit:
        """Begins a commit transaction on the document, returning a :class:`Commit` object
        that can be used to push or drop (cancel) the commit.  Each commit represents a set of
        changes that can be undone or redone as a single operation.

        If you do not call :meth:`begin_commit`, any changes made to the document will be
        committed immediately, which will result in multiple steps being added to the undo
        history.

        If you call :meth:`begin_commit`, changes made to the document will not be reflected
        in the editor until you call :meth:`push_commit`.  This allows you to group multiple
        changes into a single undo step.
        """
        command = editor_commands_pb2.BeginCommit()
        command.header.document.CopyFrom(self._doc)
        return Commit(self._kicad.send(command, editor_commands_pb2.BeginCommitResponse).id)

    def push_commit(self, commit: Commit, message: str = ""):
        """If a commit is open, pushes the changes to the document and closes the commit.  This
        will result in a single undo step being added to the undo history."""
        command = editor_commands_pb2.EndCommit()
        command.id.CopyFrom(commit.id)
        command.header.document.CopyFrom(self._doc)
        command.action = editor_commands_pb2.CommitAction.CMA_COMMIT
        command.message = message
        self._kicad.send(command, editor_commands_pb2.EndCommitResponse)

    def drop_commit(self, commit: Commit):
        """Cancels a commit, discarding any changes made since the commit was opened"""
        command = editor_commands_pb2.EndCommit()
        command.id.CopyFrom(commit.id)
        command.header.document.CopyFrom(self._doc)
        command.action = editor_commands_pb2.CommitAction.CMA_DROP
        self._kicad.send(command, editor_commands_pb2.EndCommitResponse)

    def create_items(self, items: Wrapper | Iterable[Wrapper]) -> list[_ItemT_co]:
        command = editor_commands_pb2.CreateItems()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, Wrapper):
            command.items.append(pack_any(items.proto))
        else:
            command.items.extend(pack_any(item.proto) for item in items)

        return [
            self._item_from_message(result.item)
            for result in self._kicad.send(
                command, editor_commands_pb2.CreateItemsResponse
            ).created_items
        ]

    def get_items(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[_ItemT_co]:
        """Retrieves items from the document, optionally filtering to a single or set of types.

        Providing no ``types`` filter will result in all valid types for the given document
        being retrieved on KiCad 10.0.7 and newer, and is an error on older versions."""
        return self._get_items(types, self._doc)

    def _get_items(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None,
        document: DocumentSpecifier,
    ) -> Sequence[_ItemT_co]:
        command = editor_commands_pb2.GetItems()
        command.header.document.CopyFrom(document)

        if isinstance(types, int):
            command.types.append(types)
        elif types is not None:
            command.types.extend(types)

        return [
            self._item_from_message(item)
            for item in self._kicad.send(command, editor_commands_pb2.GetItemsResponse).items
        ]

    def get_items_by_id(self, ids: KIID | Sequence[KIID]) -> Sequence[_ItemT_co]:
        """
        Retrieves items from the document by their KIID (internal unique identifier)

        .. versionadded:: 0.7.0 (KiCad 10.0.0)
        """
        command = editor_commands_pb2.GetItemsById()
        command.header.document.CopyFrom(self._doc)

        if isinstance(ids, KIID):
            command.items.append(ids)
        else:
            command.items.extend(ids)

        return [
            self._item_from_message(item)
            for item in self._kicad.send(command, editor_commands_pb2.GetItemsResponse).items
        ]

    def update_items(self, items: _ItemT_co | Sequence[_ItemT_co]) -> list[_ItemT_co]:
        """Updates the properties of one or more items in the document.  The items must already
        exist, and are matched by internal UUID.  All other properties of the items are updated
        from those passed in this call.

        Returns the updated items, which may be different from the input items if any updates
        failed to apply (for example, if any properties were out of range and were clamped)"""
        command = editor_commands_pb2.UpdateItems()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, Item):
            command.items.append(pack_any(items.proto))
        else:
            command.items.extend(pack_any(item.proto) for item in items)

        if len(command.items) == 0:
            return []

        return [
            self._item_from_message(result.item)
            for result in self._kicad.send(
                command, editor_commands_pb2.UpdateItemsResponse
            ).updated_items
        ]

    def remove_items(self, items: _ItemT_co | Sequence[_ItemT_co]):
        """Deletes one or more items from the document"""
        command = editor_commands_pb2.DeleteItems()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, Item):
            command.item_ids.append(items.id)
        else:
            command.item_ids.extend(item.id for item in items)

        if len(command.item_ids) == 0:
            return

        self._kicad.send(command, editor_commands_pb2.DeleteItemsResponse)

    def remove_items_by_id(self, items: KIID | Sequence[KIID]):
        """
        Deletes one or more items from the document using their unique IDs

        .. versionadded:: 0.4.0
        """
        command = editor_commands_pb2.DeleteItems()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, KIID):
            command.item_ids.append(items)
        else:
            command.item_ids.extend(items)

        if len(command.item_ids) == 0:
            return

        self._kicad.send(command, editor_commands_pb2.DeleteItemsResponse)

    def get_as_string(self) -> str:
        """Returns the document as a string in KiCad's native file format"""
        command = editor_commands_pb2.SaveDocumentToString()
        command.document.CopyFrom(self._doc)
        return self._kicad.send(command, editor_commands_pb2.SavedDocumentResponse).contents

    def get_selection_as_string(self) -> str:
        """Returns the current selection as a string in KiCad's native file format"""
        command = editor_commands_pb2.SaveSelectionToString()
        return self._kicad.send(command, editor_commands_pb2.SavedSelectionResponse).contents

    def get_selection(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[_ItemT_co]:
        """Retrieves the items in the current selection, optionally filtering by type"""
        command = editor_commands_pb2.GetSelection()
        command.header.document.CopyFrom(self._doc)

        if isinstance(types, int):
            command.types.append(types)
        else:
            command.types.extend(types or [])

        return [
            self._item_from_message(item)
            for item in self._kicad.send(command, editor_commands_pb2.SelectionResponse).items
        ]

    def add_to_selection(self, items: _ItemT_co | Sequence[_ItemT_co]) -> Sequence[_ItemT_co]:
        """Adds one or more items to the current selection

        :param items: The items to add to the selection
        :return: The updated selection
        """
        command = editor_commands_pb2.AddToSelection()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, Item):
            command.items.append(items.id)
        else:
            command.items.extend(item.id for item in items)

        return [
            self._item_from_message(item)
            for item in self._kicad.send(command, editor_commands_pb2.SelectionResponse).items
        ]

    def remove_from_selection(self, items: _ItemT_co | Sequence[_ItemT_co]) -> Sequence[_ItemT_co]:
        """Removes one or more items from the current selection

        :param items: The items to remove from the selection
        :return: The updated selection
        """
        command = editor_commands_pb2.RemoveFromSelection()
        command.header.document.CopyFrom(self._doc)

        if isinstance(items, Item):
            command.items.append(items.id)
        else:
            command.items.extend(item.id for item in items)

        return [
            self._item_from_message(item)
            for item in self._kicad.send(command, editor_commands_pb2.SelectionResponse).items
        ]

    def clear_selection(self):
        command = editor_commands_pb2.ClearSelection()
        command.header.document.CopyFrom(self._doc)
        self._kicad.send(command, Empty)

    def is_document_modified(self) -> bool:
        """Returns true if this document has been modified (either interactively or by the API)
        since it was last saved.

        .. versionadded:: 0.x.0 (KiCad 11)"""
        command = editor_commands_pb2.GetDocumentModifiedState()
        command.document.CopyFrom(self._doc)
        return (
            self._kicad.send(command, editor_commands_pb2.GetDocumentModifiedStateResponse).state
            == editor_commands_pb2.DocumentModifiedState.DMS_MODIFIED
        )
