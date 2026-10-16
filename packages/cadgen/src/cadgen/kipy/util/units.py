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


def from_mm(value_mm: float) -> int:
    """
    KiCad uses several internal unit systems, but for the IPC API, all distance units are defined as
    64-bit nanometers
    :param value_mm: a quantity in millimeters
    :return: the quantity in KiCad API units
    """
    return int(value_mm * 1_000_000)


def to_mm(value_nm: int) -> float:
    """
    Converts a KiCad API length/distance value (in nanometers) to millimeters
    """
    return float(value_nm) / 1_000_000


def from_mils(value_mils: float) -> int:
    """
    KiCad uses several internal unit systems, but for the IPC API, all distance units are defined
    as 64-bit nanometers
    :param value_mils: a quantity in mils (thousanths of an inch)
    :return: the quantity in KiCad API units
    """
    return int(value_mils * 25_400)


def to_mils(value_mils: int) -> float:
    """
    Converts a KiCad API length/distance value (in nanometers) to mils (thousanths of an inch)
    """
    return float(value_mils) / 25_400
