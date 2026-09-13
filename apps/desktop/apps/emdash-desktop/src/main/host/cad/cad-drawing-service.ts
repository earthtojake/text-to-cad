import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, parse, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';
import { BrowserWindow } from 'electron';
import type { CadDrawingResult } from '@core/features/browser/api';
import { findCadPythonExecutable } from '@main/host/cad/cad-runtime-service';
import { cadToolEnvironment, validateCadModel } from '@main/host/cad/cad-validation-service';

const execFileAsync = promisify(execFile);
const DRAWING_TIMEOUT_MS = 120_000;
const DRAWING_SCRIPT = String.raw`
import html
import json
import re
import sys
from build123d import Drawing, ExportDXF, ExportSVG, LineType, Pos, Unit, import_step
import ezdxf

model_path, svg_path, dxf_path, model_name, revision_id, size_json = sys.argv[1:7]
size = json.loads(size_json)
shape = import_step(model_path)
view_specs = [
    ('FRONT', (0, -1, 0), (0, 0, 1), (105, 100)),
    ('TOP', (0, 0, 1), (0, 1, 0), (105, 205)),
    ('RIGHT', (1, 0, 0), (0, 0, 1), (295, 100)),
]
drawings = []
for label, look_from, look_up, center in view_specs:
    drawing = Drawing(shape, look_from=look_from, look_up=look_up, with_hidden=True)
    box = drawing.visible_lines.bounding_box()
    width = max(box.max.X - box.min.X, 0.001)
    height = max(box.max.Y - box.min.Y, 0.001)
    scale = min(150 / width, 80 / height, 1.0)
    center_x = (box.min.X + box.max.X) * scale / 2
    center_y = (box.min.Y + box.max.Y) * scale / 2
    move = Pos(center[0] - center_x, -center[1] - center_y)
    drawings.append((label, drawing.visible_lines.scale(scale).moved(move), drawing.hidden_lines.scale(scale).moved(move), center, scale))

svg = ExportSVG(unit=Unit.MM, margin=0, precision=4)
svg.add_layer('Visible', line_weight=0.35)
svg.add_layer('Hidden', line_weight=0.18, line_type=LineType.DASHED)
for _, visible, hidden, _, _ in drawings:
    svg.add_shape(visible, layer='Visible')
    svg.add_shape(hidden, layer='Hidden')
svg.write(svg_path)

with open(svg_path, 'r', encoding='utf-8') as source:
    content = source.read()
content = re.sub(r'<svg\s+[^>]*>', '<svg width="420mm" height="297mm" viewBox="0 0 420 297" version="1.1" xmlns="http://www.w3.org/2000/svg">', content, count=1)
labels = ''.join(f'<text x="{center[0]}" y="{center[1] + 49}" text-anchor="middle">{label}</text>' for label, _, _, center, _ in drawings)
dimensions = ' × '.join(f'{float(value):.2f}' for value in size) + ' mm' if len(size) == 3 else 'See model'
revision = html.escape(revision_id.replace('sha256:', '')[:12])
name = html.escape(model_name)
annotations = f'''<g id="Annotations" font-family="Arial, sans-serif" fill="#111827" font-size="4">
  <rect x="5" y="5" width="410" height="287" fill="none" stroke="#111827" stroke-width="0.5"/>
  {labels}
  <line x1="5" y1="250" x2="415" y2="250" stroke="#111827" stroke-width="0.5"/>
  <line x1="280" y1="250" x2="280" y2="292" stroke="#111827" stroke-width="0.5"/>
  <text x="12" y="261" font-size="7" font-weight="700">{name}</text>
  <text x="12" y="271">Overall size: {dimensions}</text>
  <text x="12" y="280">General tolerances: ISO 2768-m unless otherwise specified</text>
  <text x="286" y="261">REVISION</text><text x="286" y="270" font-weight="700">{revision}</text>
  <text x="350" y="261">FORMAT</text><text x="350" y="270">A3 · mm</text>
  <text x="286" y="282">Generated from canonical CAD artifact</text>
</g>'''
content = content.replace('</svg>', annotations + '</svg>')
with open(svg_path, 'w', encoding='utf-8') as target:
    target.write(content)

dxf = ExportDXF(unit=Unit.MM)
dxf.add_layer('VISIBLE', line_weight=0.35)
dxf.add_layer('HIDDEN', line_weight=0.18, line_type=LineType.DASHED)
for _, visible, hidden, _, _ in drawings:
    dxf.add_shape(visible, layer='VISIBLE')
    dxf.add_shape(hidden, layer='HIDDEN')
dxf.write(dxf_path)
doc = ezdxf.readfile(dxf_path)
msp = doc.modelspace()
msp.add_lwpolyline([(5, -5), (415, -5), (415, -292), (5, -292), (5, -5)], dxfattribs={'layer': 'VISIBLE'})
msp.add_lwpolyline([(5, -250), (415, -250)], dxfattribs={'layer': 'VISIBLE'})
msp.add_text(model_name, height=7, dxfattribs={'layer': 'VISIBLE'}).set_placement((12, -261))
msp.add_text('REV ' + revision, height=4, dxfattribs={'layer': 'VISIBLE'}).set_placement((286, -261))
for label, _, _, center, _ in drawings:
    msp.add_text(label, height=4, dxfattribs={'layer': 'VISIBLE'}).set_placement((center[0] - 8, -(center[1] + 49)))
doc.saveas(dxf_path)
print(json.dumps({'ok': True, 'views': [item[0] for item in drawings]}))
`;

export async function createCadDrawing(input: {
  workspacePath: string;
  filePath: string;
}): Promise<CadDrawingResult> {
  const validation = await validateCadModel(input);
  if (!validation.success) return validation;
  const python = findCadPythonExecutable();
  if (!python) {
    return { success: false, error: 'The CAD Python environment is unavailable.' };
  }

  const workspacePath = resolve(input.workspacePath);
  const modelPath = join(workspacePath, validation.artifact.modelPath);
  const modelName = parse(validation.artifact.modelPath).name;
  const drawingDirectory = dirname(modelPath);
  const drawingStem = join(drawingDirectory, `${modelName}.drawing`);
  const svgPath = `${drawingStem}.svg`;
  const dxfPath = `${drawingStem}.dxf`;
  const pdfPath = `${drawingStem}.pdf`;
  const manifestPath = `${drawingStem}.json`;
  const stagingStem = `${drawingStem}.hardcore-${randomUUID()}`;
  const stagingSvgPath = `${stagingStem}.svg`;
  const stagingDxfPath = `${stagingStem}.dxf`;
  const stagingPdfPath = `${stagingStem}.pdf`;
  const stagingManifestPath = `${stagingStem}.json`;
  const stagingPaths = [stagingSvgPath, stagingDxfPath, stagingPdfPath, stagingManifestPath];
  mkdirSync(drawingDirectory, { recursive: true });

  try {
    await execFileAsync(
      python,
      [
        '-c',
        DRAWING_SCRIPT,
        modelPath,
        stagingSvgPath,
        stagingDxfPath,
        basename(modelName),
        validation.artifact.revisionId,
        JSON.stringify(validation.facts.size ?? []),
      ],
      {
        cwd: workspacePath,
        timeout: DRAWING_TIMEOUT_MS,
        maxBuffer: 5 * 1024 * 1024,
        env: cadToolEnvironment(),
      }
    );
    await renderSvgPdf(stagingSvgPath, stagingPdfPath);
    const manifest = {
      version: 1,
      kind: 'engineering-drawing',
      model: validation.artifact,
      facts: validation.facts,
      outputs: {
        svg: relativeDrawingPath(workspacePath, svgPath),
        pdf: relativeDrawingPath(workspacePath, pdfPath),
        dxf: relativeDrawingPath(workspacePath, dxfPath),
      },
      generatedAt: new Date().toISOString(),
    };
    writeFileSync(stagingManifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
    renameSync(stagingSvgPath, svgPath);
    renameSync(stagingDxfPath, dxfPath);
    renameSync(stagingPdfPath, pdfPath);
    renameSync(stagingManifestPath, manifestPath);
    return {
      success: true,
      revisionId: validation.artifact.revisionId,
      drawing: {
        svgPath: relativeDrawingPath(workspacePath, svgPath),
        pdfPath: relativeDrawingPath(workspacePath, pdfPath),
        dxfPath: relativeDrawingPath(workspacePath, dxfPath),
        manifestPath: relativeDrawingPath(workspacePath, manifestPath),
      },
    };
  } catch (error) {
    return { success: false, error: drawingErrorMessage(error) };
  } finally {
    for (const stagingPath of stagingPaths) {
      if (existsSync(stagingPath)) rmSync(stagingPath);
    }
  }
}

function drawingErrorMessage(error: unknown): string {
  const stderr =
    typeof error === 'object' && error !== null && 'stderr' in error
      ? String((error as { stderr?: unknown }).stderr ?? '')
      : '';
  const detail = stderr
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1);
  return detail ? `Drawing generation failed: ${detail}` : 'Drawing generation failed.';
}

async function renderSvgPdf(svgPath: string, pdfPath: string): Promise<void> {
  const window = new BrowserWindow({
    show: false,
    width: 1400,
    height: 990,
    webPreferences: { sandbox: true },
  });
  try {
    await window.loadURL(pathToFileURL(svgPath).toString());
    const pdf = await window.webContents.printToPDF({
      landscape: true,
      pageSize: 'A3',
      printBackground: true,
      margins: { top: 0, bottom: 0, left: 0, right: 0 },
    });
    const temporary = `${pdfPath}.hardcore-${randomUUID()}.tmp`;
    try {
      writeFileSync(temporary, pdf);
      renameSync(temporary, pdfPath);
    } finally {
      if (existsSync(temporary)) rmSync(temporary);
    }
  } finally {
    window.destroy();
  }
}

function relativeDrawingPath(workspacePath: string, path: string): string {
  return path
    .slice(workspacePath.length + 1)
    .split('\\')
    .join('/');
}
