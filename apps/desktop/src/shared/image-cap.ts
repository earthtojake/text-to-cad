/**
 * The largest image, in bytes of the file itself, an agent may be handed.
 *
 * The model rejects an image over 5 MB, and a rejected tool result stays in the
 * transcript for good, so the ceiling is the model's rather than memory's. It
 * measures the base64 the image travels as, which is 4/3 of the file: the cap
 * on the file's own bytes is the 5 MiB divided by that. Main checks files it
 * reads (`attach_snapshot`); the renderer fits the captures it makes to it.
 */
export const MAX_IMAGE_BYTES = Math.floor(5 * 1024 * 1024 * 3 / 4);
