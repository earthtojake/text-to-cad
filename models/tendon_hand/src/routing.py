"""The tendon hand's routing studies: tendons and reaction liners as swept solids.

The four-lane Bowden prototype, the six-lane MCP-yaw transport, the middle finger's
full routing, and the thumb CMC's six transports with the candidate that replaced
their atlas. Each model was its own script in `models/tendon_hand/src/`; they share
nothing expensive, so none is a `@memo` and no model calls another.
"""

from cadgen import model

import build123d as bd

from lib.axis_transport import crossover
from lib.bowden_guide import make_bowden_body
from lib.bowden_universal import FOUR_LANES, bowden_universal
from lib.finger_routing import MIDDLE, middle_finger_routes, yaw_drive_plane
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.thumb_cmc_transport import thumb_cmc_packet
from lib.transport_guide import make_guide, make_tendon

# The thumb CMC candidate's atlas: its six rows' parameters and Bezier curves.
CANDIDATE = [{'flex': 0.0,
  'yaw': 0.0,
  'outlet_y': 16,
  'rows': [{'lane': -4.2,
            'length': 40,
            'params': [5.847677841769557,
                       5.707750484390268,
                       -1.9322460949092362,
                       -5.1714789197492905,
                       6.891449362938922,
                       -0.5448816235185499,
                       2.2765459894926328,
                       2.644607403515762,
                       -2.628531519837251,
                       5.942379756902715,
                       5.510565840920439,
                       0.08767958920924696,
                       2.184560564578951,
                       -4.277164651136985],
            'curves': [[[-4.2, -12.25, 0.0],
                        [-0.8459097825888415, -7.459862741571028, 0.0],
                        [-1.3873644713906863, -7.448024909241923, 4.24684195942316],
                        [-1.9322460949092362, -5.1714789197492905, 6.891449362938922]],
                       [[-1.9322460949092362, -5.1714789197492905, 6.891449362938922],
                        [-2.477127718427786, -2.8949329302566578, 9.536056766454685],
                        [-2.716211109046498, 3.7578191923237636, 9.787730492057424],
                        [-2.628531519837251, 5.942379756902715, 5.510565840920439]],
                       [[-2.628531519837251, 5.942379756902715, 5.510565840920439],
                        [-2.5408519306280044, 8.126940321481666, 1.2334011897834536],
                        [-0.9, 10.292249515609733, -5.5],
                        [-0.9, 16.0, -5.5]]]},
           {'lane': 4.2,
            'length': 40,
            'params': [5.798323331934775,
                       5.945355239456141,
                       4.501622242748377,
                       -4.568703842546244,
                       10.830264998555243,
                       -1.4815995363329064,
                       2.298590968248186,
                       4.234386226765572,
                       2.1689162741951873,
                       5.565180189726618,
                       12.284334341517848,
                       -0.507691261151043,
                       2.036386045336605,
                       -2.6151053594574805],
            'curves': [[[4.2, -12.25, 0.0],
                        [7.525781633542271, -7.500291589197071, 0.0],
                        [5.983221779081283, -6.86729481079443, 6.595878771789671],
                        [4.501622242748377, -4.568703842546244, 10.830264998555243]],
                       [[4.501622242748377, -4.568703842546244, 10.830264998555243],
                        [3.020022706415471, -2.2701128742980576, 15.064651225320816],
                        [2.67660753534623, 3.5287941443900133, 14.899439700975329],
                        [2.1689162741951873, 5.565180189726618, 12.284334341517848]],
                       [[2.1689162741951873, 5.565180189726618, 12.284334341517848],
                        [1.6612250130441444, 7.601566235063223, 9.669228982060368],
                        [0.9, 10.054644760543859, 5.5],
                        [0.9, 16.0, 5.5]]]},
           {'lane': -5.4,
            'length': 36,
            'params': [6.394280823816141,
                       6.280816489682174,
                       -4.3487913348171485,
                       -5.9322223353459185,
                       -7.607255016899612,
                       -2.1723932703905398,
                       1.8142157579665674,
                       -2.778114300869054,
                       -5.54082972033498,
                       5.205829679580151,
                       -7.489064418532686,
                       0.43662700761463047,
                       2.1552678630051276,
                       3.146793118554548],
            'curves': [[[-5.4, -12.25, 0.0],
                        [-1.7323911920477073, -7.012111791413109, 0.0],
                        [-2.1763980644266088, -7.746438093312486, -4.829140716030558],
                        [-4.3487913348171485, -5.9322223353459185, -7.607255016899612]],
                       [[-4.3487913348171485, -5.9322223353459185, -7.607255016899612],
                        [-6.521184605207688, -4.118006577379351, -10.385369317768665],
                        [-5.97745672794961, 3.0505618165750232, -10.635857537087233],
                        [-5.54082972033498, 5.205829679580151, -7.489064418532686]],
                       [[-5.54082972033498, 5.205829679580151, -7.489064418532686],
                        [-5.104202712720349, 7.361097542585279, -4.342271299978138],
                        [-5.4, 5.969183510317826, 0.0],
                        [-5.4, 12.25, 0.0]]]},
           {'lane': 5.4,
            'length': 36,
            'params': [6.394280823816141,
                       6.280816489682174,
                       6.451208665182852,
                       -5.9322223353459185,
                       -7.607255016899612,
                       -2.1723932703905398,
                       1.8142157579665674,
                       -2.778114300869054,
                       5.259170279665021,
                       5.205829679580151,
                       -7.489064418532686,
                       0.43662700761463047,
                       2.1552678630051276,
                       3.146793118554548],
            'curves': [[[5.4, -12.25, 0.0],
                        [9.067608807952293, -7.012111791413109, 0.0],
                        [8.623601935573392, -7.746438093312486, -4.829140716030558],
                        [6.451208665182852, -5.9322223353459185, -7.607255016899612]],
                       [[6.451208665182852, -5.9322223353459185, -7.607255016899612],
                        [4.278815394792312, -4.118006577379351, -10.385369317768665],
                        [4.822543272050391, 3.0505618165750232, -10.635857537087233],
                        [5.259170279665021, 5.205829679580151, -7.489064418532686]],
                       [[5.259170279665021, 5.205829679580151, -7.489064418532686],
                        [5.695797287279651, 7.361097542585279, -4.342271299978138],
                        [5.4, 5.969183510317826, 0.0],
                        [5.4, 12.25, 0.0]]]},
           {'lane': -3.0,
            'length': 36,
            'params': [2.0052727011966267,
                       2.6147113987409223,
                       1.2768823676509955,
                       -8.114311668845634,
                       -3.683890266841107,
                       0.11006099819886593,
                       1.14148581345449,
                       -3.788249223886027,
                       -4.496557064461925,
                       -2.599002459141762,
                       -7.4923597391,
                       -0.19039575528101538,
                       4.679436966113975,
                       1.1319679080365186,
                       -4.361825326324119,
                       6.984160482168352,
                       -2.6189224240822893,
                       -0.045018642842697146,
                       1.327384517737971,
                       2.4411535665075825],
            'curves': [[[-3.0, -12.25, 0.0],
                        [-1.8498228301356028, -10.607376767457875, 0.0],
                        [1.1668213694521297, -9.255797482300125, 0.10435895704492015],
                        [1.2768823676509955, -8.114311668845634, -3.683890266841107]],
                       [[1.2768823676509955, -8.114311668845634, -3.683890266841107],
                        [1.3869433658498613, -6.972825855391144, -7.472139490727134],
                        [-4.30616130918091, -7.278439425255737, -8.62432764713652],
                        [-4.496557064461925, -2.599002459141762, -7.4923597391]],
                       [[-4.496557064461925, -2.599002459141762, -7.4923597391],
                        [-4.68695281974294, 2.0804345069722134, -6.360391831063482],
                        [-4.316806683481422, 5.6567759644303806, -5.060075990589872],
                        [-4.361825326324119, 6.984160482168352, -2.6189224240822893]],
                       [[-4.361825326324119, 6.984160482168352, -2.6189224240822893],
                        [-4.406843969166816, 8.311544999906323, -0.17776885757470673],
                        [-3.0, 9.635288601259077, 0.0],
                        [-3.0, 12.25, 0.0]]]},
           {'lane': 3.0,
            'length': 36,
            'params': [4.222154832589407,
                       4.2554167365848015,
                       5.627725273675428,
                       -5.630230440356396,
                       -4.137609781928311,
                       -0.6725231193464096,
                       0.72423446321625,
                       -3.228142105297843,
                       2.070874500931308,
                       -0.49225361394402295,
                       -9.416352334686781,
                       0.04378326808810865,
                       3.1552588502541736,
                       -0.03875659597211541,
                       3.345773437805546,
                       5.205629033848913,
                       -3.874550458685295,
                       -0.05547668363409596,
                       0.6371338875008374,
                       3.1175930688469307],
            'curves': [[[3.0, -12.25, 0.0],
                        [5.421728522598979, -8.791413237579741, 0.0],
                        [6.300248393021837, -6.354464903572646, -0.9094676766304679],
                        [5.627725273675428, -5.630230440356396, -4.137609781928311]],
                       [[5.627725273675428, -5.630230440356396, -4.137609781928311],
                        [4.955202154329019, -4.905995977140146, -7.365751887226153],
                        [2.0270912328431994, -3.6475124641981966, -9.377595738714666],
                        [2.070874500931308, -0.49225361394402295, -9.416352334686781]],
                       [[2.070874500931308, -0.49225361394402295, -9.416352334686781],
                        [2.1146577690194164, 2.6630052363101506, -9.455108930658897],
                        [3.401250121439642, 4.568495146348075, -6.9921435275322255],
                        [3.345773437805546, 5.205629033848913, -3.874550458685295]],
                       [[3.345773437805546, 5.205629033848913, -3.874550458685295],
                        [3.29029675417145, 5.842762921349751, -0.7569573898383641],
                        [3.0, 7.9945832634151985, 0.0],
                        [3.0, 12.25, 0.0]]]}]}]


@model
def bowden_review():
    """Four-lane two-axis neutral reaction guide prototype at neutral pose."""
    children = []
    for i, lane in enumerate(FOUR_LANES, 1):
        route = bowden_universal(0, 0, lane)
        children.append(make_bowden_body(route["path"], f"lane_{i:02d}_tendon"))
        children.append(make_bowden_body(route["path"], f"lane_{i:02d}_reaction_liner", liner=True))
    return bd.Compound(label="four_lane_universal_bowden_geometry_prototype", children=children)


@model
def transport_review():
    """Exact six-lane MCP-yaw transport prototype; supports remain separate work."""
    bodies = []
    for i in range(6):
        route = crossover(i, 6, angle_deg=0, angle_range=(-20, 20))
        bodies.append(make_tendon(route["path"], f"channel_{i + 1:02d}_continuous_tendon"))
        bodies.append(make_guide(route["path"][0], f"channel_{i + 1:02d}_parent_inlet_guide"))
        bodies.append(make_guide(route["path"][2], f"channel_{i + 1:02d}_child_outlet_guide"))
    return bd.Compound(label="coaxial_transport_six_lane_geometry_prototype", children=bodies)


@model
def middle_routing_review():
    """Middle finger full routing prototype from palm input to eight terminations."""
    children = []
    f = MIDDLE
    y = f.base_y
    for i, (length, width) in enumerate(zip(f.lengths, f.widths)):
        shape = make_phalanx(length, width, distal=i == 2, label=f"middle_link_{i + 1:02d}")
        children.append(bd.Pos(f.x, y, 0) * shape)
        y += length
    targets = [("mcp_abduction", f.base_y, 5.5, "yaw"), ("mcp_flexion", f.base_y, 5.5, "flex"),
               ("pip", f.base_y + f.lengths[0], 4.5, "flex"), ("dip", f.base_y + sum(f.lengths[:2]), 3.5, "flex")]
    for target, y, radius, axis in targets:
        for sign, suffix in ((1, "positive"), (-1, "negative")):
            shape = make_pulley(radius, label=f"middle_{target}_{suffix}_drive_pulley")
            if axis == "yaw":
                placement = bd.Pos(f.x, y, yaw_drive_plane(sign))
            else:
                placement = bd.Pos(f.x + sign * .9, y, 0) * bd.Rot(0, 90, 0)
            children.append(placement * shape)
    for route in middle_finger_routes():
        children.append(make_tendon(route["path"], route["name"]))
        for group in route["groups"]:
            if group["guide"] in ("snug_reaction_liner", "fixed_curved_guide"):
                children.append(make_bowden_body(group["path"], group["label"], liner=True))
    return bd.Compound(label="middle_finger_full_tendon_routing_prototype", children=children)


@model
def thumb_cmc_transport_review():
    """Six neutral CMC tendon and reaction-liner swept solids for strict validation."""
    children = []
    for row in thumb_cmc_packet():
        children.append(make_bowden_body(row["path"], row["tendon"] + "_cmc_tendon"))
        children.append(make_bowden_body(row["path"], row["tendon"] + "_cmc_reaction_liner", liner=True))
    return bd.Compound(label="thumb_cmc_six_continuous_reaction_transports", children=children)


@model
def thumb_cmc_candidate_review():
    """The six CMC transports with the candidate atlas above, outlet at y 16."""
    children = []
    for row in thumb_cmc_packet(atlas_override=CANDIDATE, outlet_y=16.):
        children.append(make_bowden_body(row["path"], row["tendon"] + "_cmc_tendon"))
        children.append(make_bowden_body(row["path"], row["tendon"] + "_cmc_reaction_liner", liner=True))
    return bd.Compound(label="thumb_cmc_six_continuous_reaction_transports", children=children)


if __name__ == "__main__":
    bowden_review()
    transport_review()
    middle_routing_review()
    thumb_cmc_transport_review()
    thumb_cmc_candidate_review()
