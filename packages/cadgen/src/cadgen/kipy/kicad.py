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

"""Classes for interacting with KiCad at a high level"""

from __future__ import annotations

import os
import platform
import random
import string
import sys
import time
from collections.abc import Sequence
from tempfile import gettempdir
from typing import cast

from google.protobuf.empty_pb2 import Empty

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from cadgen.kipy.board import Board
from cadgen.kipy.board_types import Footprint
from cadgen.kipy.client import ApiError, KiCadClient
from cadgen.kipy.common_types import (
    CompoundShape,
    LibraryIdentifier,
    LibraryStatus,
    PathType,
    Text,
    TextBox,
)
from cadgen.kipy.errors import FutureVersionError, LibraryCommandError
from cadgen.kipy.geometry import Box2
from cadgen.kipy.kicad_api_version import KICAD_API_VERSION
from cadgen.kipy.project import Project
from cadgen.kipy.proto.board import board_types_pb2
from cadgen.kipy.proto.common import commands
from cadgen.kipy.proto.common.commands import (
    base_commands_pb2,
    editor_commands_pb2,
    library_commands_pb2,
    project_commands_pb2,
)
from cadgen.kipy.proto.common.types import DocumentSpecifier, DocumentType, base_types_pb2

# Re-exported protobuf enum types
from cadgen.kipy.proto.common.types.library_types_pb2 import (
    LibraryCommandStatus,
    LibraryLoadStatus,
    LibraryTableScope,
    LibraryType,
)
from cadgen.kipy.proto.schematic import schematic_types_pb2
from cadgen.kipy.schematic import Schematic
from cadgen.kipy.schematic_types import SchematicSymbol
from cadgen.kipy.server import KiCadServer, find_kicad_cli
from cadgen.kipy.util import unpack_any

_UNKNOWN_API_VERSION = "unknown"


def _default_socket_path() -> str:
    path = os.environ.get("KICAD_API_SOCKET")
    if path is not None:
        return path
    if platform.system() == "Windows":
        return f"ipc://{gettempdir()}\\kicad\\api.sock"
    else:
        # Check for default socket path of KiCad flatpak on flathub
        home = os.environ.get("HOME")
        if home is not None:
            flatpak_socket_path = f"{home}/.var/app/org.kicad.KiCad/cache/tmp/kicad/api.sock"
            if os.path.exists(flatpak_socket_path):
                return f"ipc://{flatpak_socket_path}"

        return "ipc:///tmp/kicad/api.sock"


def _random_client_name() -> str:
    return "anonymous-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _default_kicad_token() -> str:
    token = os.environ.get("KICAD_API_TOKEN")
    if token is not None:
        return token
    return ""


class KiCadVersion:
    def __init__(self, major: int, minor: int, patch: int, full_version: str):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.full_version = full_version

    @staticmethod
    def from_proto(proto: base_types_pb2.KiCadVersion) -> KiCadVersion:
        return KiCadVersion(proto.major, proto.minor, proto.patch, proto.full_version)

    @staticmethod
    def from_git_describe(describe: str) -> KiCadVersion:
        if not describe:
            return KiCadVersion(0, 0, 0, _UNKNOWN_API_VERSION)

        parts = describe.split("-")
        version_part = parts[0]

        try:
            major, minor, patch = map(int, version_part.split("."))
        except ValueError:
            return KiCadVersion(0, 0, 0, describe)

        if len(parts) > 1:
            additional_info = "-".join(parts[1:])
            return KiCadVersion(major, minor, patch, f"{version_part}-{additional_info}")

        return KiCadVersion(major, minor, patch, f"{version_part}")

    def __repr__(self):
        return f"{self.major}.{self.minor}.{self.patch} ({self.full_version})"

    def __eq__(self, other):
        if not isinstance(other, KiCadVersion):
            return NotImplemented

        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other):
        if not isinstance(other, KiCadVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other


class KiCad:
    def __init__(
        self,
        socket_path: str | None = None,
        client_name: str | None = None,
        kicad_token: str | None = None,
        timeout_ms: int = 2000,
        headless: bool = False,
        kicad_cli_path: str | None = None,
        file_path: str | None = None,
    ):
        """Creates a connection to a running KiCad instance

        :param socket_path: The path to the IPC API socket (leave default to read from the
            KICAD_API_SOCKET environment variable, which will be set automatically by KiCad when
            launching API plugins, or to use the default platform-dependent socket path if the
            environment variable is not set).
        :param client_name: A unique name identifying this plugin instance.  Leave default to
            generate a random client name.
        :param kicad_token: A token that can be provided to the client to uniquely identify a
            KiCad instance.  Leave default to read from the KICAD_API_TOKEN environment variable.
        :param timeout_ms: The maximum time to wait for a response from KiCad, in milliseconds
        :param headless: Start and connect to a headless ``kicad-cli api-server`` instance.
        :param kicad_cli_path: Optional path to ``kicad-cli``.
        :param file_path: Optional path to a board, schematic, or project file to pre-load in headless mode.
        """
        self._server: KiCadServer | None = None

        if headless:
            if socket_path is not None:
                raise ValueError("socket_path cannot be used when headless=True")

            cli_path = find_kicad_cli(kicad_cli_path)
            server = KiCadServer(cli_path, file_path=file_path)
            server.start()
            server.wait_for_ready(timeout_s=max(float(timeout_ms) / 1000.0, 5.0))
            self._server = server
            socket_path = server.socket_url

        if socket_path is None:
            socket_path = _default_socket_path()
        if client_name is None:
            client_name = _random_client_name()
        if kicad_token is None:
            kicad_token = _default_kicad_token()

        try:
            self._client = KiCadClient(socket_path, client_name, kicad_token, timeout_ms)
        except Exception:
            if self._server is not None:
                self._server.stop()
                self._server = None
            raise

    @staticmethod
    def from_client(client: KiCadClient):
        """Creates a KiCad object from an existing KiCad client"""
        k = KiCad.__new__(KiCad)
        k._client = client
        k._server = None
        return k

    def close(self):
        """Close the KiCad connection and stop any headless server started by this object."""
        if hasattr(self, "_client"):
            self._client.close()

        if self._server is not None:
            self._server.stop()
            self._server = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def __del__(self):
        self.close()

    def get_version(self) -> KiCadVersion:
        """Returns the KiCad version as a string, including any package-specific info"""
        response = self._client.send(commands.GetVersion(), commands.GetVersionResponse)
        return KiCadVersion.from_proto(response.version)

    def get_api_version(self) -> KiCadVersion:
        """Returns the version of KiCad that this library was built against"""
        return KiCadVersion.from_git_describe(KICAD_API_VERSION)

    def check_version(self) -> bool:
        """Checks if the connected KiCad version matches the version this library was built against"""
        kicad_version = self.get_version()
        api_version = self.get_api_version()

        if api_version.full_version == _UNKNOWN_API_VERSION:
            return True

        if kicad_version > api_version:
            raise FutureVersionError(
                f"Warning: Connected KiCad version ({kicad_version}) is newer than "
                f"the API version of kicad-python ({api_version})"
            )

        return True

    def ping(self):
        self._client.send(commands.Ping(), Empty)

    def get_kicad_binary_path(self, binary_name: str) -> str:
        """Returns the full path to the given KiCad binary

        :param binary_name: The short name of the binary, such as ``kicad-cli`` or ``kicad-cli.exe``.
                            If on Windows, an `.exe` extension will be assumed if not present.
        :return: The full path to the binary
        """
        cmd = commands.GetKiCadBinaryPath()
        cmd.binary_name = binary_name
        return self._client.send(cmd, commands.PathResponse).path

    def get_paths(self) -> dict[PathType.ValueType, str]:
        """Returns a dictionary mapping well-known KiCad filesystem paths to
        their locations.  Paths are returned in platform-native format.  Not every
        path is guaranteed to exist and be accessible.  The meaning and contents of
        this dictionary are not covered by API stability guarantees and may change
        between KiCad versions.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        cmd = base_commands_pb2.GetPaths()
        response = self._client.send(cmd, base_commands_pb2.GetPathsResponse)
        return {entry.type: entry.path for entry in response.paths}

    def get_plugin_settings_path(self, identifier: str) -> str:
        """Return a writeable path that a plugin can use for storing persistent data such as
        configuration files, etc.  This path may not yet exist; actual creation of the directory
        for a given plugin is up to the plugin itself.  Files in this path will not be modified if
        the plugin is uninstalled or upgraded.

        :param identifier: should be the full identifier of the plugin (e.g. org.kicad.myplugin)
        :return: a path, with local separators, that the plugin can use for storing settings
        """
        cmd = commands.GetPluginSettingsPath()
        cmd.identifier = identifier
        return self._client.send(cmd, commands.StringResponse).response

    def run_action(self, action: str):
        """Runs a KiCad tool action, if it is available

        WARNING: This is an unstable API and is not intended for use other
        than by API developers. KiCad does not guarantee the stability of
        action names, and running actions may have unintended side effects.
        :param action: the name of a KiCad TOOL_ACTION
        :return: a value from the KIAPI.COMMON.COMMANDS.RUN_ACTION_STATUS enum
        """
        command = commands.RunAction()
        command.action = action
        return self._client.send(command, commands.RunActionResponse)

    def get_open_documents(self, doc_type: DocumentType.ValueType) -> Sequence[DocumentSpecifier]:
        """Retrieves a list of open documents matching the given type"""
        command = commands.GetOpenDocuments()
        command.type = doc_type
        response = self._client.send(command, commands.GetOpenDocumentsResponse)
        return response.documents

    def open_document(self, path: str, type: DocumentType.ValueType) -> DocumentSpecifier:
        """In headless mode, opens a document.  Not currently supported for GUI mode.

        .. versionadded:: 0.7.0
        """
        command = project_commands_pb2.OpenDocument()
        command.path = path
        command.type = type
        response = self._client.send(command, project_commands_pb2.OpenDocumentResponse)
        return response.document

    def close_document(self, document: DocumentSpecifier):
        """In headless mode, closes an open document.  Not currently supported for GUI mode.

        .. versionadded:: 0.7.0
        """
        command = project_commands_pb2.CloseDocument()
        command.document.CopyFrom(document)
        self._client.send(command, Empty)

    def create_document(self, path: str, type: DocumentType.ValueType) -> DocumentSpecifier:
        """In headless mode, creates a new document.  Not currently supported for GUI mode.
        The new document is created in memory only; call
        :meth:`~kipy.editor.EditorCommandsHandler.save` to persist to disk.
        A project will be created for the document if it doesn't already exist.
        Returns an error if the current document is unsaved: save or revert first.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = project_commands_pb2.CreateDocument()
        command.path = path
        command.type = type
        response = self._client.send(command, project_commands_pb2.OpenDocumentResponse)
        return response.document

    def open_library_item(
        self,
        library: str,
        name: str,
        type: DocumentType.ValueType,
    ):
        """Loads a library item (e.g. a footprint) into the matching editor.

        At present, only ``DOCTYPE_FOOTPRINT`` is supported by KiCad; the
        footprint editor must already be open.

        :param library: The library nickname.
        :param name: The entry name within the library.
        :param type: The document type of the item to load.
        """
        command = editor_commands_pb2.OpenLibraryItem()
        command.type = type
        command.identifier.library_nickname = library
        command.identifier.entry_name = name
        self._client.send(command, Empty)

    def get_project(self, document: DocumentSpecifier) -> Project:
        """Returns a Project object for the given document"""
        return Project(self._client, document)

    def get_board(self) -> Board:
        """Retrieves a reference to the PCB open in KiCad, if one exists"""
        docs = self.get_open_documents(DocumentType.DOCTYPE_PCB)
        if len(docs) == 0:
            raise ApiError("Expected to be able to retrieve at least one board")
        return Board(self._client, docs[0])

    def get_schematic(self) -> Schematic:
        """
        .. versionadded:: 0.x.y (KiCad 11)
        """
        docs = self.get_open_documents(DocumentType.DOCTYPE_SCHEMATIC)
        if len(docs) == 0:
            raise ApiError("Expected to be able to retrieve at least one schematic")
        # The returned specifier may carry the sheet the KiCad UI currently has open;
        # drop it so that queries cover all sheets; for_sheet() can be used to specify one.
        doc = docs[0]
        doc.ClearField("sheet_path")
        return Schematic(self._client, doc)

    def get_library_items(
        self, type: LibraryType.ValueType, nicknames: Sequence[str] = ()
    ) -> Sequence[LibraryIdentifier]:
        """Retrieves the identifiers of all items contained in the given library or libraries

        Library loading happens asynchronously after KiCad starts up, so this command may
        return an empty list if the requested libraries have not finished loading yet.
        Use :meth:`wait_for_libraries` to wait until the libraries you need have finished
        loading.

        :param type: The type of library to query
        :param nicknames: The library nickname(s) to query.  If empty, all libraries of the
            given type are queried.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = library_commands_pb2.GetLibraryItems()
        command.type = type
        command.nickname.extend(nicknames)
        response = self._client.send(command, library_commands_pb2.LibraryItemsResponse)
        return [LibraryIdentifier(item) for item in response.items]

    def get_library_symbols(self, nicknames: Sequence[str] = ()) -> Sequence[LibraryIdentifier]:
        """Retrieves the identifiers of all symbols contained in the given library or libraries

        See :meth:`get_library_items` for caveats about asynchronous library loading.

        :param nicknames: The library nickname(s) to query.  If empty, all symbol libraries
            are queried.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        return self.get_library_items(LibraryType.LT_SYMBOL, nicknames)

    def get_library_footprints(self, nicknames: Sequence[str] = ()) -> Sequence[LibraryIdentifier]:
        """Retrieves the identifiers of all footprints contained in the given library or
        libraries

        See :meth:`get_library_items` for caveats about asynchronous library loading.

        :param nicknames: The library nickname(s) to query.  If empty, all footprint
            libraries are queried.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        return self.get_library_items(LibraryType.LT_FOOTPRINT, nicknames)

    def get_library_symbol(
        self, lib_id: LibraryIdentifier | str, document: DocumentSpecifier | None = None
    ) -> SchematicSymbol:
        """Retrieves the definition of a symbol from a library

        Requires the libraries to have been loaded already.  Use :meth:`load_all_libraries`
        first in headless contexts.

        :param lib_id: The symbol to retrieve, either as a :class:`LibraryIdentifier` or a
            string such as ``"Device:R"``.
        :param document: Optional document specifier used to enable project-specific
            libraries; if not given, only global libraries are searched.
        :return: The symbol definition.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        return cast(
            SchematicSymbol, self._get_library_item(LibraryType.LT_SYMBOL, lib_id, document)
        )

    def get_library_footprint(
        self, lib_id: LibraryIdentifier | str, document: DocumentSpecifier | None = None
    ) -> Footprint:
        """Retrieves the definition of a footprint from a library

        Requires the libraries to have been loaded already.  Use :meth:`load_all_libraries`
        first in headless contexts.

        :param lib_id: The footprint to retrieve, either as a :class:`LibraryIdentifier` or a
            string such as ``"Resistor_SMD:R_0603_1608Metric"``.
        :param document: Optional document specifier used to enable project-specific
            libraries; if not given, only global libraries are searched.
        :return: The footprint definition.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        return cast(Footprint, self._get_library_item(LibraryType.LT_FOOTPRINT, lib_id, document))

    def _get_library_item(
        self,
        library_type: LibraryType.ValueType,
        lib_id: LibraryIdentifier | str,
        document: DocumentSpecifier | None,
    ) -> SchematicSymbol | Footprint:
        command = library_commands_pb2.GetItemsFromLibrary()
        command.type = library_type

        if document is not None:
            command.document.CopyFrom(document)

        if isinstance(lib_id, str):
            library, _, name = lib_id.partition(":")
            if name == "":
                raise ValueError("lib_id must be in the format <nickname>:<item name>")
            command.item_ids.add(library_nickname=library, entry_name=name)
        else:
            command.item_ids.add().CopyFrom(lib_id.proto)

        response = self._client.send(command, editor_commands_pb2.GetItemsResponse)

        if response.status != base_types_pb2.ItemRequestStatus.IRS_OK:
            raise ApiError(f"Failed to retrieve library item: {response.status}")

        if len(response.items) == 0:
            raise ApiError("Requested item was not found in the library")

        concrete = unpack_any(response.items[0])

        if isinstance(concrete, schematic_types_pb2.SchematicSymbol):
            return SchematicSymbol(proto=concrete)

        if isinstance(concrete, board_types_pb2.Footprint):
            return Footprint(proto=concrete)

        raise ApiError(f"Unexpected item type received from library: {type(concrete).__name__}")

    def get_library_statuses(
        self,
        types: LibraryType.ValueType | Sequence[LibraryType.ValueType] | None = None,
        scope: LibraryTableScope.ValueType = LibraryTableScope.LTS_BOTH,
    ) -> Sequence[LibraryStatus]:
        """Retrieves the load status of each library in the given table scope(s)

        :param types: The type(s) of library to query.  If not given, all types are queried.
        :param scope: Which table scope(s) to query (global, project, or both).
        :return: One :class:`LibraryStatus` per enabled library row in the queried tables.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = library_commands_pb2.GetLibraryStatuses()

        if types is not None:
            if isinstance(types, int):
                command.types.append(types)
            else:
                command.types.extend(types)

        command.scope = scope
        response = self._client.send(command, library_commands_pb2.LibraryStatusResponse)
        return [LibraryStatus(entry) for entry in response.libraries]

    def load_all_libraries(
        self,
        types: LibraryType.ValueType | Sequence[LibraryType.ValueType] | None = None,
    ):
        """Starts a background load of all libraries of the given type(s) that are listed
        in the library tables

        This command is only available in headless (command-line) mode; in GUI mode KiCad
        preloads libraries on its own.  The load proceeds asynchronously; use
        :meth:`wait_for_libraries` to wait for it to finish.

        NOTE: KiCad may need to load the schematic and PCB editor dynamic libraries if they
        have not been loaded already prior to this call (such as if you call this right after
        starting ``kicad-cli``).  In this case, KiCad may briefly stop responding to API messages,
        which can cause transient timeout errors if your connection timeout is set to a low value.

        :param types: The type(s) of library to load.  If not given, all types are loaded.
        :raise: :class:`LibraryCommandError` if the load request could not be processed.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = library_commands_pb2.LoadAllLibraries()

        if types is not None:
            if isinstance(types, int):
                command.type.append(types)
            else:
                command.type.extend(types)

        status = self._client.send(command, LibraryCommandStatus)

        if status.code != LibraryCommandStatus.Code.LCS_OK:
            raise LibraryCommandError(status.error_message, code=status.code)

    def reload_library(
        self,
        type: LibraryType.ValueType,
        scope: LibraryTableScope.ValueType,
        nicknames: Sequence[str] = (),
    ):
        """Reloads library table row(s) from disk

        The reload process operates asynchronously; updated library content will not be
        available until the load has completed.  Use :meth:`wait_for_libraries` to wait
        for the reload to finish.

        :param type: The type of library to reload.
        :param scope: Which table to look up the libraries in.  ``LTS_BOTH`` is not valid
            here; choose one table.
        :param nicknames: The library nickname(s) to reload.  If empty, all libraries
            matching the given type and scope are reloaded.
        :raise: :class:`LibraryCommandError` if one of the given nicknames could not be reloaded
            (usually because the nickname could not be found in the library tables).

        .. versionadded:: 0.x.y (KiCad 11)
        """
        if type == LibraryTableScope.LTS_BOTH:
            raise ValueError("LTS_BOTH is not valid for reload_library")

        command = library_commands_pb2.ReloadLibrary()
        command.type = type
        command.scope = scope
        command.nickname.extend(nicknames)
        status = self._client.send(command, LibraryCommandStatus)

        if status.code != LibraryCommandStatus.Code.LCS_OK:
            raise LibraryCommandError(status.error_message, code=status.code)

    def wait_for_libraries(
        self,
        types: LibraryType.ValueType | Sequence[LibraryType.ValueType] | None = None,
        interval_ms: int = 500,
        timeout_s: float = 60.0,
        scope: LibraryTableScope.ValueType = LibraryTableScope.LTS_BOTH,
    ) -> Sequence[LibraryStatus]:
        """Waits until no queried libraries are still loading, polling with
        :meth:`get_library_statuses`.

        :param types: The type(s) of library to wait for.  If not given, all types are
            waited for.
        :param interval_ms: How long to sleep between status polls, in milliseconds.
        :param timeout_s: Maximum time to wait, in seconds, before raising
            :class:`TimeoutError`.
        :param scope: Which table scope(s) to query.
        :return: The final status of each library.  Libraries whose status is not
            ``LLS_LOADED`` did not finish loading; check :attr:`LibraryStatus.error_message`
            on those entries for details.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        deadline = time.monotonic() + timeout_s
        statuses: Sequence[LibraryStatus] = []

        while True:
            statuses = self.get_library_statuses(types, scope)

            if all(entry.status != LibraryLoadStatus.LLS_LOADING for entry in statuses):
                return statuses

            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for libraries to finish loading")

            time.sleep(interval_ms / 1000.0)

    # Utility functions

    def get_text_extents(self, text: Text) -> Box2:
        """Returns the bounding box of the given text object"""
        cmd = base_commands_pb2.GetTextExtents()
        cmd.text.CopyFrom(text.proto)
        reply = self._client.send(cmd, base_types_pb2.Box2)
        return Box2.from_proto(reply)

    def get_text_as_shapes(
        self, texts: Text | TextBox | Sequence[Text | TextBox]
    ) -> list[CompoundShape]:
        """Returns polygonal shapes representing the given text objects"""
        if isinstance(texts, (Text, TextBox)):
            texts = [texts]

        cmd = base_commands_pb2.GetTextAsShapes()
        for t in texts:
            inner = base_commands_pb2.TextOrTextBox()
            if isinstance(t, Text):
                inner.text.CopyFrom(t.proto)
            else:
                inner.textbox.CopyFrom(t.proto)
            cmd.text.append(inner)

        reply = self._client.send(cmd, base_commands_pb2.GetTextAsShapesResponse)

        return [CompoundShape(entry.shapes) for entry in reply.text_with_shapes]
