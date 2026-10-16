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

from cadgen.kipy.proto.board.board_types_pb2 import BoardLayer

_B = BoardLayer

COPPER_LAYERS: tuple[BoardLayer.ValueType, ...] = (
    (_B.BL_F_Cu,)
    + (
        _B.BL_In1_Cu,
        _B.BL_In2_Cu,
        _B.BL_In3_Cu,
        _B.BL_In4_Cu,
        _B.BL_In5_Cu,
        _B.BL_In6_Cu,
        _B.BL_In7_Cu,
        _B.BL_In8_Cu,
        _B.BL_In9_Cu,
        _B.BL_In10_Cu,
        _B.BL_In11_Cu,
        _B.BL_In12_Cu,
        _B.BL_In13_Cu,
        _B.BL_In14_Cu,
        _B.BL_In15_Cu,
        _B.BL_In16_Cu,
        _B.BL_In17_Cu,
        _B.BL_In18_Cu,
        _B.BL_In19_Cu,
        _B.BL_In20_Cu,
        _B.BL_In21_Cu,
        _B.BL_In22_Cu,
        _B.BL_In23_Cu,
        _B.BL_In24_Cu,
        _B.BL_In25_Cu,
        _B.BL_In26_Cu,
        _B.BL_In27_Cu,
        _B.BL_In28_Cu,
        _B.BL_In29_Cu,
        _B.BL_In30_Cu,
    )
    + (_B.BL_B_Cu,)
)
"""The sequence of copper layers, top to bottom"""

FRONT_TECH_LAYERS: frozenset[BoardLayer.ValueType] = frozenset(
    (_B.BL_F_Mask, _B.BL_F_Adhes, _B.BL_F_Paste, _B.BL_F_SilkS, _B.BL_F_CrtYd, _B.BL_F_Fab)
)
"""Technical layers associated with the front of a board"""

BACK_TECH_LAYERS: frozenset[BoardLayer.ValueType] = frozenset(
    (_B.BL_B_Mask, _B.BL_B_Adhes, _B.BL_B_Paste, _B.BL_B_SilkS, _B.BL_B_CrtYd, _B.BL_B_Fab)
)
"""Technical layers associated with the back of a board"""

TECHNICAL_LAYERS: frozenset[BoardLayer.ValueType] = FRONT_TECH_LAYERS | BACK_TECH_LAYERS
"""All technical layers on the board (front and back sides)"""

USER_LAYERS: frozenset[BoardLayer.ValueType] = frozenset(
    (
        _B.BL_User_1,
        _B.BL_User_2,
        _B.BL_User_3,
        _B.BL_User_4,
        _B.BL_User_5,
        _B.BL_User_6,
        _B.BL_User_7,
        _B.BL_User_8,
        _B.BL_User_9,
        _B.BL_User_10,
        _B.BL_User_11,
        _B.BL_User_12,
        _B.BL_User_13,
        _B.BL_User_14,
        _B.BL_User_15,
        _B.BL_User_16,
        _B.BL_User_17,
        _B.BL_User_18,
        _B.BL_User_19,
        _B.BL_User_20,
        _B.BL_User_21,
        _B.BL_User_22,
        _B.BL_User_23,
        _B.BL_User_24,
        _B.BL_User_25,
        _B.BL_User_26,
        _B.BL_User_27,
        _B.BL_User_28,
        _B.BL_User_29,
        _B.BL_User_30,
        _B.BL_User_31,
        _B.BL_User_32,
        _B.BL_User_33,
        _B.BL_User_34,
        _B.BL_User_35,
        _B.BL_User_36,
        _B.BL_User_37,
        _B.BL_User_38,
        _B.BL_User_39,
        _B.BL_User_40,
        _B.BL_User_41,
        _B.BL_User_42,
        _B.BL_User_43,
        _B.BL_User_44,
        _B.BL_User_45,
    )
)
"""The user-assignable drawing layers on a board (not all boards will have all layers)"""

DRAWING_LAYERS: frozenset[BoardLayer.ValueType] = frozenset(
    (
        _B.BL_Dwgs_User,
        _B.BL_Cmts_User,
        _B.BL_Eco1_User,
        _B.BL_Eco2_User,
        _B.BL_Edge_Cuts,
        _B.BL_Margin,
    )
)
"""The built-in drawing layers on a board"""


CANONICAL_LAYER_NAMES = {
    BoardLayer.BL_F_Cu: "F.Cu",
    BoardLayer.BL_In1_Cu: "In1.Cu",
    BoardLayer.BL_In2_Cu: "In2.Cu",
    BoardLayer.BL_In3_Cu: "In3.Cu",
    BoardLayer.BL_In4_Cu: "In4.Cu",
    BoardLayer.BL_In5_Cu: "In5.Cu",
    BoardLayer.BL_In6_Cu: "In6.Cu",
    BoardLayer.BL_In7_Cu: "In7.Cu",
    BoardLayer.BL_In8_Cu: "In8.Cu",
    BoardLayer.BL_In9_Cu: "In9.Cu",
    BoardLayer.BL_In10_Cu: "In10.Cu",
    BoardLayer.BL_In11_Cu: "In11.Cu",
    BoardLayer.BL_In12_Cu: "In12.Cu",
    BoardLayer.BL_In13_Cu: "In13.Cu",
    BoardLayer.BL_In14_Cu: "In14.Cu",
    BoardLayer.BL_In15_Cu: "In15.Cu",
    BoardLayer.BL_In16_Cu: "In16.Cu",
    BoardLayer.BL_In17_Cu: "In17.Cu",
    BoardLayer.BL_In18_Cu: "In18.Cu",
    BoardLayer.BL_In19_Cu: "In19.Cu",
    BoardLayer.BL_In20_Cu: "In20.Cu",
    BoardLayer.BL_In21_Cu: "In21.Cu",
    BoardLayer.BL_In22_Cu: "In22.Cu",
    BoardLayer.BL_In23_Cu: "In23.Cu",
    BoardLayer.BL_In24_Cu: "In24.Cu",
    BoardLayer.BL_In25_Cu: "In25.Cu",
    BoardLayer.BL_In26_Cu: "In26.Cu",
    BoardLayer.BL_In27_Cu: "In27.Cu",
    BoardLayer.BL_In28_Cu: "In28.Cu",
    BoardLayer.BL_In29_Cu: "In29.Cu",
    BoardLayer.BL_In30_Cu: "In30.Cu",
    BoardLayer.BL_B_Cu: "B.Cu",
    BoardLayer.BL_B_Adhes: "B.Adhes",
    BoardLayer.BL_F_Adhes: "F.Adhes",
    BoardLayer.BL_B_Paste: "B.Paste",
    BoardLayer.BL_F_Paste: "F.Paste",
    BoardLayer.BL_B_SilkS: "B.SilkS",
    BoardLayer.BL_F_SilkS: "F.SilkS",
    BoardLayer.BL_B_Mask: "B.Mask",
    BoardLayer.BL_F_Mask: "F.Mask",
    BoardLayer.BL_Dwgs_User: "Dwgs.User",
    BoardLayer.BL_Cmts_User: "Cmts.User",
    BoardLayer.BL_Eco1_User: "Eco1.User",
    BoardLayer.BL_Eco2_User: "Eco2.User",
    BoardLayer.BL_Edge_Cuts: "Edge.Cuts",
    BoardLayer.BL_Margin: "Margin",
    BoardLayer.BL_F_CrtYd: "F.CrtYd",
    BoardLayer.BL_B_CrtYd: "B.CrtYd",
    BoardLayer.BL_F_Fab: "F.Fab",
    BoardLayer.BL_B_Fab: "B.Fab",
    BoardLayer.BL_User_1: "User.1",
    BoardLayer.BL_User_2: "User.2",
    BoardLayer.BL_User_3: "User.3",
    BoardLayer.BL_User_4: "User.4",
    BoardLayer.BL_User_5: "User.5",
    BoardLayer.BL_User_6: "User.6",
    BoardLayer.BL_User_7: "User.7",
    BoardLayer.BL_User_8: "User.8",
    BoardLayer.BL_User_9: "User.9",
    BoardLayer.BL_Rescue: "Rescue",
    BoardLayer.BL_User_10: "User.10",
    BoardLayer.BL_User_11: "User.11",
    BoardLayer.BL_User_12: "User.12",
    BoardLayer.BL_User_13: "User.13",
    BoardLayer.BL_User_14: "User.14",
    BoardLayer.BL_User_15: "User.15",
    BoardLayer.BL_User_16: "User.16",
    BoardLayer.BL_User_17: "User.17",
    BoardLayer.BL_User_18: "User.18",
    BoardLayer.BL_User_19: "User.19",
    BoardLayer.BL_User_20: "User.20",
    BoardLayer.BL_User_21: "User.21",
    BoardLayer.BL_User_22: "User.22",
    BoardLayer.BL_User_23: "User.23",
    BoardLayer.BL_User_24: "User.24",
    BoardLayer.BL_User_25: "User.25",
    BoardLayer.BL_User_26: "User.26",
    BoardLayer.BL_User_27: "User.27",
    BoardLayer.BL_User_28: "User.28",
    BoardLayer.BL_User_29: "User.29",
    BoardLayer.BL_User_30: "User.30",
    BoardLayer.BL_User_31: "User.31",
    BoardLayer.BL_User_32: "User.32",
    BoardLayer.BL_User_33: "User.33",
    BoardLayer.BL_User_34: "User.34",
    BoardLayer.BL_User_35: "User.35",
    BoardLayer.BL_User_36: "User.36",
    BoardLayer.BL_User_37: "User.37",
    BoardLayer.BL_User_38: "User.38",
    BoardLayer.BL_User_39: "User.39",
    BoardLayer.BL_User_40: "User.40",
    BoardLayer.BL_User_41: "User.41",
    BoardLayer.BL_User_42: "User.42",
    BoardLayer.BL_User_43: "User.43",
    BoardLayer.BL_User_44: "User.44",
    BoardLayer.BL_User_45: "User.45",
}


def is_copper_layer(layer: BoardLayer.ValueType) -> bool:
    """Checks if the given layer is a copper layer"""
    return layer in COPPER_LAYERS


def canonical_name(layer: BoardLayer.ValueType) -> str:
    """Returns the canonical name of the given layer identifier.  This is the name that is used in
    the KiCad user interface if the user has not set a custom layer name, and in the KiCad file
    formats in various places."""
    return CANONICAL_LAYER_NAMES.get(layer, "Unknown")


def layer_from_canonical_name(name: str) -> BoardLayer.ValueType:
    """Returns the layer identifier for the given canonical layer name, or BL_UNKNOWN if the name
    is not recognized."""
    for layer, layer_name in CANONICAL_LAYER_NAMES.items():
        if layer_name == name:
            return layer
    return BoardLayer.BL_UNKNOWN


def iter_copper_layers():
    """Yields all copper layers."""
    yield from COPPER_LAYERS
