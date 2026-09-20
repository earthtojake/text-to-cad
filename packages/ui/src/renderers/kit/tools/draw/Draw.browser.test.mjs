import { test } from 'node:test';
import { runDrawScenario } from '../../../harness/drawScenario.mjs';

// Under the shell (kit/shell), mounted by the smallest renderer built on it: a one-triangle mesh file.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

test('Draw locks the view, pans model and ink together, keeps tools, colors and fills, and discards the sketch when left', t => runDrawScenario(t, {
  file: 'part.stl',
  entries: root => [{ kind: 'stl', file: 'part.stl', rootRelativeFile: 'part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }],
  assets: { '/mesh.stl': mesh },
}));
