"""Keep cadgen's authored material independent of build123d's colour-setting property.

Installed when build123d finishes loading, without loading the kernel early. Native
build123d material assignments still use its property. A cadgen Material remains an
authored value: the document resolves inheritance and explicit colours at build time.
"""

from typing import Any


def install(build123d: Any) -> None:
    shape = build123d.Shape
    original = shape.material
    if getattr(original.fget, "__cadgen_material__", False):
        return

    def read(self: Any) -> Any:
        if "material" in self.__dict__:
            return self.__dict__["material"]
        return original.fget(self)

    def write(self: Any, value: Any) -> None:
        from cadgen.engine.materials import Material

        if isinstance(value, Material):
            self.__dict__["material"] = value
            self._material = None
        else:
            original.fset(self, value)
            self.__dict__.pop("material", None)

    read.__cadgen_material__ = True
    shape.material = property(read, write, doc=original.__doc__)
