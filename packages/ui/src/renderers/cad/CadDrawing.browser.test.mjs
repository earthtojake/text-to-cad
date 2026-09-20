import { test } from 'node:test';
import { runDrawScenario } from '../harness/drawScenario.mjs';

// The CAD renderer still mounts Draw in its own frame (CadFileView, CadRenderPane,
// CadViewer) rather than the shell's, so the kit's scenario runs here too, over
// the smallest file this renderer opens without a backend: a robot of two boxes.
const urdf = `<?xml version="1.0"?>
<robot name="pair">
  <link name="base"><visual><geometry><box size="0.4 0.4 0.1"/></geometry></visual></link>
  <link name="arm"><visual><origin xyz="0.25 0 0"/><geometry><box size="0.5 0.08 0.08"/></geometry></visual></link>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="arm"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/><limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
</robot>
`;

test('Draw in the CAD renderer\'s own frame: the same flow over a robot', t => runDrawScenario(t, {
  file: 'pair.urdf',
  entries: root => [{ kind: 'urdf', file: 'pair.urdf', rootRelativeFile: 'pair.urdf', url: '/pair.urdf', hash: `${root}-urdf`, bytes: urdf.length }],
  assets: { '/pair.urdf': urdf },
}));
