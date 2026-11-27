// zip.mjs: the little of the zip format this host needs, with no dependency: a wheel's entries read (to leave some
// out), and an archive written of entries copied as they are or stored anew. No zip64, no encryption: a wheel has
// neither, and nothing here is over 4 GB.

const CRC = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(data) {
  let crc = 0xffffffff;
  for (let i = 0; i < data.length; i++) crc = CRC[(crc ^ data[i]) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** A zip's entries, from its central directory: each its name, method, sizes, crc and its data as stored. */
export function readEntries(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = bytes.length - 22;
  while (end >= 0 && view.getUint32(end, true) !== 0x06054b50) end--;
  if (end < 0) throw new Error("not a zip: no end of central directory");
  const count = view.getUint16(end + 10, true);
  let at = view.getUint32(end + 16, true);
  const entries = [];
  const text = new TextDecoder();
  for (let i = 0; i < count; i++) {
    if (view.getUint32(at, true) !== 0x02014b50) throw new Error("not a zip: bad central directory");
    const method = view.getUint16(at + 10, true), crc = view.getUint32(at + 16, true);
    const packed = view.getUint32(at + 20, true), size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true), extra = view.getUint16(at + 30, true), comment = view.getUint16(at + 32, true);
    const local = view.getUint32(at + 42, true);
    const name = text.decode(bytes.subarray(at + 46, at + 46 + nameLength));
    const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
    entries.push({ name, method, crc, size, data: bytes.subarray(start, start + packed) });
    at += 46 + nameLength + extra + comment;
  }
  return entries;
}

/**
 * A zip of `entries`: each `{ name, data }` stored as it is, or one of `readEntries`' copied with its compression
 * (`method`, `crc`, `size` given). Dated 1980-01-01, so the same entries are the same bytes.
 */
export function writeZip(entries) {
  const encoder = new TextEncoder();
  const parts = [], central = [];
  let offset = 0;
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const method = entry.method ?? 0, data = entry.data;
    const crc = entry.crc ?? crc32(data), size = entry.size ?? data.length;
    const head = new DataView(new ArrayBuffer(30));
    head.setUint32(0, 0x04034b50, true); head.setUint16(4, 20, true); head.setUint16(8, method, true); head.setUint16(12, 33, true);
    head.setUint32(14, crc, true); head.setUint32(18, data.length, true); head.setUint32(22, size, true); head.setUint16(26, name.length, true);
    const row = new DataView(new ArrayBuffer(46));
    row.setUint32(0, 0x02014b50, true); row.setUint16(4, 20, true); row.setUint16(6, 20, true); row.setUint16(10, method, true);
    row.setUint16(14, 33, true); row.setUint32(16, crc, true); row.setUint32(20, data.length, true); row.setUint32(24, size, true);
    row.setUint16(28, name.length, true); row.setUint32(42, offset, true);
    parts.push(new Uint8Array(head.buffer), name, data);
    central.push(new Uint8Array(row.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
  end.setUint32(12, centralSize, true); end.setUint32(16, offset, true);
  const out = new Uint8Array(offset + centralSize + 22);
  let at = 0;
  for (const part of [...parts, ...central, new Uint8Array(end.buffer)]) { out.set(part, at); at += part.length; }
  return out;
}
