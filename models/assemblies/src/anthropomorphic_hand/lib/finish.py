"""Four hardware surface languages, plus dyed braided tendon fibers."""

FINISHES = {
    "aluminum": ("#a9b7c1", {"roughness": .34, "metalness": .86, "clearcoat": .12}),
    "dark": ("#17242d", {"roughness": .32, "metalness": .68, "clearcoat": .16}),
    "steel": ("#d3dbe1", {"roughness": .12, "metalness": .98, "clearcoat": .25}),
    "pad": ("#ede8da", {"roughness": .67, "metalness": .01, "clearcoat": .04}),
    "tendon_flex": ("#d67436", {"roughness": .57, "metalness": .03}),
    "tendon_extend": ("#f1d3a1", {"roughness": .60, "metalness": .02}),
}


def finish(shape, language, label):
    from cadgen import srgb
    color, material = FINISHES[language]
    shape.label = label
    shape.color = srgb(color)
    shape.cad_material = dict(material)
    return shape
