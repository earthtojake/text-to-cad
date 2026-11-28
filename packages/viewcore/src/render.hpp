// render.hpp: a still of a scene, drawn in software (render.cpp). The scene is what cad's renderer hands OpenGL,
// said in plain numbers: the meshes as the engine's XBM2 buffers, each instance's placement and material, the
// lights, the camera (hosts/node/README.md, "Stills").
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace vc {

// The picture of `scene` (JSON), its payloads end to end in `blob` (the scene's "payloads" lists their lengths):
// width x height RGBA bytes, sRGB, the top row first; or a PNG of them where the scene's "format" is "png".
std::string render(const std::string& scene, const uint8_t* blob, size_t size);

}  // namespace vc
