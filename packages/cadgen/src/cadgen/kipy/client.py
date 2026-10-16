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

from typing import TypeVar

import pynng
from google.protobuf.message import Message

from cadgen.kipy.errors import ApiError, ConnectionError
from cadgen.kipy.proto.common import ApiRequest, ApiResponse, ApiStatusCode


class KiCadClient:
    def __init__(self, socket_path: str, client_name: str, kicad_token: str, timeout_ms: int):
        self._socket_path = socket_path
        self._client_name = client_name
        self._kicad_token = kicad_token
        self._timeout_ms = timeout_ms
        self._connected = False

    def close(self):
        if self._connected:
            self._conn.close()
            self._connected = False

    def _connect(self):
        if self._connected:
            self._conn.close()

        try:
            self._conn = pynng.Req0(
                dial=self._socket_path,
                block_on_dial=True,
                send_timeout=self._timeout_ms,
                recv_timeout=self._timeout_ms,
            )
            self._connected = True
        except pynng.exceptions.NNGException as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to KiCad: {e}") from None

    @property
    def connected(self):
        return self._connected

    R = TypeVar("R", bound=Message)

    def send(self, command: Message, response_type: type[R]) -> R:
        if not self._connected:
            self._connect()

        envelope = ApiRequest()
        envelope.message.Pack(command)
        envelope.header.kicad_token = self._kicad_token
        envelope.header.client_name = self._client_name

        try:
            self._conn.send(envelope.SerializeToString())
        except pynng.exceptions.NNGException as e:
            raise ConnectionError(f"Failed to send command to KiCad: {e}") from None

        try:
            reply_data = self._conn.recv_msg()
        except pynng.exceptions.NNGException as e:
            raise ConnectionError(f"Error receiving reply from KiCad: {e}") from None

        reply = ApiResponse()
        reply.ParseFromString(reply_data.bytes)

        if reply.status.status == ApiStatusCode.AS_OK:
            response = response_type()

            if not reply.message.Unpack(response):
                raise ApiError(
                    f"Failed to unpack {response_type.__name__} from the response to {type(command).__name__}"
                )

            if self._kicad_token == "":
                self._kicad_token = reply.header.kicad_token

            return response
        else:
            raise ApiError(
                f"KiCad returned error: {reply.status.error_message}",
                raw_message=reply.status.error_message,
                code=reply.status.status,
            )
