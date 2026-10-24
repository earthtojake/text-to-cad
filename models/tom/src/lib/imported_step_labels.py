"""Use stable ASCII vendor labels for an exact geometry re-export."""
import re


def decoded_labels(shape):
    for node in (shape, *shape.descendants):
        label = node.label
        decoded = re.sub(r'\\X2\\([0-9A-Fa-f]+)\\X0\\',
            lambda m: bytes.fromhex(m.group(1)).decode('utf-16-be'), label)
        # Current STEP round-tripping misreads UTF-8 feature names as Latin-1.
        # Preserve a deterministic identity without changing any geometry.
        node.label = ''.join(c if ord(c)<128 else f'u{ord(c):04x}' for c in decoded)
    return shape
