import { test } from 'node:test';
import { runDrawScenario } from '../harness/drawScenario.mjs';

// The CAD renderer still mounts Draw in its own frame (CadFileView, CadRenderPane,
// CadViewer) rather than the shell's, so the kit's scenario runs here too, over
// the smallest file this renderer opens without a backend: a plate with one hole.
const dxf = [
  '0', 'SECTION', '2', 'HEADER', '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES',
  '0', 'LWPOLYLINE', '8', 'CUT', '90', '4', '70', '1', '10', '0', '20', '0', '10', '40', '20', '0', '10', '40', '20', '20', '10', '0', '20', '20',
  '0', 'CIRCLE', '8', 'CUT', '10', '20', '20', '10', '40', '4',
  '0', 'ENDSEC', '0', 'EOF', ''
].join('\n');

test('Draw in the CAD renderer\'s own frame: the same flow over a drawing', t => runDrawScenario(t, {
  file: 'plate.dxf',
  entries: root => [{ kind: 'dxf', file: 'plate.dxf', rootRelativeFile: 'plate.dxf', url: '/plate.dxf', hash: `${root}-dxf`, bytes: dxf.length }],
  assets: { '/plate.dxf': dxf },
}));
