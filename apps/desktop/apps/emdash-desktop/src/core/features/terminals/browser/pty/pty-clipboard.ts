const OSC_52_CLIPBOARD_TARGET = 'c';

export function decodeOsc52ClipboardData(data: string): string | null {
  const separatorIndex = data.indexOf(';');
  if (separatorIndex === -1) return null;

  const target = data.slice(0, separatorIndex);
  if (target !== '' && !target.includes(OSC_52_CLIPBOARD_TARGET)) return null;

  const encoded = data.slice(separatorIndex + 1).replace(/\s/g, '');
  if (!encoded || encoded === '?') return null;

  try {
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}
