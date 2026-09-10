import { GIFEncoder, quantize, applyPalette } from 'gifenc';
const encoder = GIFEncoder();
self.onmessage = ({ data }) => {
  try {
    if (data.finish) {
      encoder.finish(); const bytes = encoder.bytes();
      self.postMessage({ bytes }, [bytes.buffer]);
    } else {
      const rgba = new Uint8Array(data.rgba), palette = quantize(rgba, 256);
      encoder.writeFrame(applyPalette(rgba, palette), data.width, data.height, { palette, delay: data.delay, repeat: 0 });
      self.postMessage({ ready: true });
    }
  } catch (error) { self.postMessage({ error: error.message }); }
};
