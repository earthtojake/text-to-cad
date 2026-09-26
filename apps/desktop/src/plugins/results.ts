/** A tool result carrying an image, as the MCP bridge hands it to the agent. */
export async function imageResult(blob: Blob, metadata: object) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
  return { ...metadata, mimeType: blob.type, base64: btoa(binary) };
}
