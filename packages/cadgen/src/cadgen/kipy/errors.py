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

from cadgen.kipy.proto.common import ApiStatusCode
from cadgen.kipy.proto.common.types.library_types_pb2 import LibraryCommandStatus


class ConnectionError(Exception):
    """Raised when a connection to KiCad cannot be established"""


class ApiError(Exception):
    """Raised when KiCad returns an error from an API call.  This indicates that the communcation
    was successful, but the API call failed for some reason."""

    def __init__(
        self,
        message: str,
        raw_message: str = "",
        code: ApiStatusCode.ValueType = ApiStatusCode.AS_BAD_REQUEST,
    ):
        super().__init__(message)
        self._raw_message = raw_message
        self._code = code

    @property
    def code(self) -> ApiStatusCode.ValueType:
        return self._code

    @property
    def raw_message(self) -> str:
        return self._raw_message


class FutureVersionError(Exception):
    """Raised when a version check shows that kicad-python is talking to a version of KiCad
    newer than the one it was built against"""


class LibraryCommandError(Exception):
    """Raised when KiCad returns an error from a library command"""

    def __init__(
        self,
        message: str,
        raw_message: str = "",
        code: LibraryCommandStatus.Code.ValueType = LibraryCommandStatus.Code.LCS_ERROR,
    ):
        super().__init__(message)
        self._raw_message = raw_message
        self._code = code

    @property
    def code(self) -> LibraryCommandStatus.Code.ValueType:
        return self._code

    @property
    def raw_message(self) -> str:
        return self._raw_message
