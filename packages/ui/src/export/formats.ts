import { isDocumentId } from '@cad/core/lib/cadRefs.js';
import { isMeshRenderFormat } from '@cad/core/lib/fileFormats.js';
import type { ExportFormat } from '@cad/core/client';
import type { ExportView } from './context.js';

/**
 * One item of the Export menu: what the server writes, its name there, the file's extension, and
 * whether the file carries the animations the document's code made (an engine document's GLB).
 */
export interface ExportChoice {
  /** `label`: a format's own name, as it is written everywhere (STEP, Gerbers); `labelKey`: a word the
   * page's language says (Drill), which the menu says in it. */
  format: ExportFormat; label: string; labelKey?: string; extension: string; animations?: true;
  /** The usage count's name where it is not `export_<format>` (a control's name is letters and underscores). */
  control?: string;
}

const STEP: ExportChoice = { format: 'step', label: 'STEP', extension: '.step' };
const STL: ExportChoice = { format: 'stl', label: 'STL', extension: '.stl' };
const THREEMF: ExportChoice = { format: 'threemf', label: '3MF', extension: '.3mf' };
const GLB: ExportChoice = { format: 'glb', label: 'GLB', extension: '.glb' };
const ANIMATED_GLB: ExportChoice = { ...GLB, animations: true };
const DXF: ExportChoice = { format: 'dxf', label: 'DXF', extension: '.dxf' };
const XBF: ExportChoice = { format: 'xbf', label: 'XBF', extension: '.xbf' };
// An xbf's XBF is the file itself, as it is on disk: an xbf is not written from another.
const ORIGINAL: ExportChoice = { format: 'original', label: 'XBF', extension: '.xbf' };
// A KiCad board's, each written by KiCad (`cad kicad_pcb export --to <format>`), named as the server names
// the download: a folder of files (the Gerbers, the drill files, the two PDF pages) is one .zip.
const BOARD: ExportChoice[] = [
  { format: 'gerbers', label: 'Gerbers', extension: '-gerbers.zip' },
  { format: 'drill', label: '', labelKey: 'export.format.drill', extension: '-drill.zip' },
  { format: 'pos', label: '', labelKey: 'export.format.position', extension: '-pos.csv' },
  { format: 'bom', label: 'BOM', extension: '-bom.csv' },
  { format: 'step', label: 'STEP', extension: '.step' },
  { format: 'glb', label: 'GLB', extension: '.glb' },
  { format: 'odb', label: 'ODB++', extension: '-odb.zip' },
  { format: 'ipc2581', label: 'IPC-2581', extension: '-ipc2581.xml', control: 'export_ipc' },
  { format: 'pdf', label: 'PDF', extension: '-pdf.zip' },
  { format: 'dxf', label: 'DXF', extension: '-outline.dxf' },
];

// A KiCad schematic's, each written by KiCad (`cad kicad_sch export --to <format>`): the PDF of every sheet,
// an SVG a sheet (one .zip), KiCad's netlist and the BOM.
const SCHEMATIC: ExportChoice[] = [
  { format: 'pdf', label: 'PDF', extension: '.pdf' },
  { format: 'svg', label: 'SVG', extension: '-svg.zip' },
  { format: 'netlist', label: '', labelKey: 'export.format.netlist', extension: '.net' },
  { format: 'bom', label: 'BOM', extension: '-bom.csv' },
];

/**
 * What the file on screen saves as, from its kind and what the view already holds, so the menu has
 * nothing to wait for: an engine document (a STEP, an xbf, a model held by its id) as STEP, STL,
 * 3MF, GLB and XBF, and DXF where the view draws it flat (`planar`); a mesh held by its id (an
 * implicit's, by its `kind`) as each of the three mesh kinds; a mesh file as the other two
 * mesh kinds; a KiCad board as each of KiCad's fabrication, assembly and 3D files; a KiCad schematic as
 * KiCad's PDF, SVGs, netlist and BOM. A format a document
 * cannot be written in is its job's to refuse, saying why. Any other file has none.
 */
export function exportChoices({ file, planar, kind }: Pick<ExportView, 'file' | 'planar' | 'kind'>): ExportChoice[] {
  const drawing = planar ? [DXF] : [];
  if (isDocumentId(file) && kind && isMeshRenderFormat(kind)) return [STL, THREEMF, GLB];
  if (isDocumentId(file) || /\.(?:step|stp)$/i.test(file)) return [STEP, STL, THREEMF, ANIMATED_GLB, ...drawing, XBF];
  if (/\.xbf$/i.test(file)) return [STEP, STL, THREEMF, ANIMATED_GLB, ...drawing, ORIGINAL];
  if (/\.glb$/i.test(file)) return [STL, THREEMF];
  if (/\.stl$/i.test(file)) return [THREEMF, GLB];
  if (/\.3mf$/i.test(file)) return [STL, GLB];
  if (/\.kicad_pcb$/i.test(file)) return BOARD;
  if (/\.kicad_sch$/i.test(file)) return SCHEMATIC;
  return [];
}
