import { isDocumentId } from '@text-to-cad/core/lib/cadRefs.js';
import type { ExportFormat } from '@text-to-cad/core/client';
import type { ExportView } from './context.js';

/**
 * One item of the Export menu: what the server writes, its name there, the file's extension, and
 * whether the file carries the animations the document's code made (an engine document's GLB).
 */
export interface ExportChoice { format: ExportFormat; label: string; extension: string; animations?: true }

const STEP: ExportChoice = { format: 'step', label: 'STEP', extension: '.step' };
const STL: ExportChoice = { format: 'stl', label: 'STL', extension: '.stl' };
const THREEMF: ExportChoice = { format: 'threemf', label: '3MF', extension: '.3mf' };
const GLB: ExportChoice = { format: 'glb', label: 'GLB', extension: '.glb' };
const ANIMATED_GLB: ExportChoice = { ...GLB, animations: true };
const DXF: ExportChoice = { format: 'dxf', label: 'DXF', extension: '.dxf' };
const XBF: ExportChoice = { format: 'xbf', label: 'XBF', extension: '.xbf' };
// An xbf's XBF is the file itself, as it is on disk: an xbf is not written from another.
const ORIGINAL: ExportChoice = { format: 'original', label: 'XBF', extension: '.xbf' };

/**
 * What the file on screen saves as, from its kind and what the view already holds, so the menu has
 * nothing to wait for: an engine document (a STEP, an xbf, a model held by its id) as STEP, STL,
 * 3MF, GLB and XBF, and DXF where the view draws it flat (`planar`); a mesh file as the other two
 * mesh kinds. A format a document cannot be written in is its job's to refuse, saying why. Any
 * other file has none.
 */
export function exportChoices({ file, planar }: Pick<ExportView, 'file' | 'planar'>): ExportChoice[] {
  const drawing = planar ? [DXF] : [];
  if (isDocumentId(file) || /\.(?:step|stp)$/i.test(file)) return [STEP, STL, THREEMF, ANIMATED_GLB, ...drawing, XBF];
  if (/\.xbf$/i.test(file)) return [STEP, STL, THREEMF, ANIMATED_GLB, ...drawing, ORIGINAL];
  if (/\.glb$/i.test(file)) return [STL, THREEMF];
  if (/\.stl$/i.test(file)) return [THREEMF, GLB];
  if (/\.3mf$/i.test(file)) return [STL, GLB];
  return [];
}
