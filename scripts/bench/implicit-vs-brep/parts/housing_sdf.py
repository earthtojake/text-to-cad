from cadgen import implicit as im


@im.part(out="../out/housing_sdf.glb", resolution=0.5)
def housing():
    body = im.box((30, 30, 20), radius=2).named("body")
    bore = im.cylinder(radius=8, height=40).named("bore")
    boss = im.cylinder(radius=5, height=8).translate(0, 0, 14).named("boss")
    holes = im.cylinder(radius=1.6, height=30).translate(11, 11, 0).mirror("x").mirror("y").named("holes")
    return im.union(body - bore, boss, round=1.5) - holes


if __name__ == "__main__":
    housing()
