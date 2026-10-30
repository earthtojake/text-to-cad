import { describe, expect, it } from 'vitest';
import { besideEnd, chromeCovers, clearAlong, colourBarCover, framingInset, panelInset, roomAlong, settleLabels } from './feaChrome.js';

describe('a load\'s label on screen', () => {
  it('sits just past the outer end of its own arrow, running on the way it points', () => {
    // An arrow pushing down: its free end is its tail, above; the label stands over it, centred.
    expect(besideEnd([100, 50], [100, 90], 10, 14)).toEqual({ x: 100, y: 33, align: 'center' });
    // Leaning right or left: beside it, reading away from the arrow.
    expect(besideEnd([100, 50], [80, 50], 10)).toEqual({ x: 110, y: 50, align: 'left' });
    expect(besideEnd([100, 50], [120, 50], 10)).toEqual({ x: 90, y: 50, align: 'right' });
    // Seen end on: to its right.
    expect(besideEnd([100, 50], [100.5, 50], 10)).toEqual({ x: 110, y: 50, align: 'left' });
  });

  it('slides along its own arrow\'s line just past the part when its spot at the tail is over it, never across the model\'s box', () => {
    // The part covers the line up to 37 px past the tail: the label stands just past it, within a few px.
    const clear = (distance: number) => distance >= 37;
    const slid = clearAlong(clear, 400)!;
    expect(slid).toBeGreaterThanOrEqual(37);
    expect(slid).toBeLessThan(37 + 400 / 2 ** 6 + 1e-9);
    // Clear at the tail: it stays there. Over the part all the way to the view's edge: no place on the line.
    expect(clearAlong(() => true, 400)).toBe(0);
    expect(clearAlong(() => false, 400)).toBeNull();
    // The room on the line before the view's edge, a margin in: rightwards from x 100 in a 500 px view.
    expect(roomAlong(100, 50, 1, 0, 500, 300, 8)).toBe(392);
    expect(roomAlong(100, 50, 0, -1, 500, 300, 8)).toBe(42);
  });

  it('moves out from under the panels at the left, and two labels never sit on each other', () => {
    const cover = { left: 8, top: 40, right: 172, bottom: 780 };
    // "0 Pa" at an outlet behind the Study panel: right of it, reading on from there.
    const [outlet] = settleLabels([{ x: 120, y: 335, align: 'left', width: 30 }], cover);
    expect(outlet).toMatchObject({ x: 176, y: 335, align: 'left' });
    // Clear of the panel: where it was.
    expect(settleLabels([{ x: 400, y: 335, align: 'left', width: 30 }], cover)[0]).toMatchObject({ x: 400, y: 335 });
    // "400 N" and "1 g down" drawn on the same spot: the second is nudged clear of the first.
    const [load, weight] = settleLabels([{ x: 715, y: 160, align: 'center', width: 36 }, { x: 720, y: 164, align: 'left', width: 44 }], null);
    expect(load).toMatchObject({ x: 715, y: 160 });
    expect(Math.abs(weight.y - load.y)).toBeGreaterThanOrEqual(14);
  });

  it('moves a label from under the toolbar strip centred at the view\'s top to just below it, and leaves one clear of it', () => {
    const strip = { left: 380, top: 8, right: 620, bottom: 44 };
    const [under] = settleLabels([{ x: 500, y: 30, align: 'left', width: 40 }], [strip], { bounds: { width: 1000, height: 700 } });
    expect(under).toMatchObject({ x: 500, y: 55, align: 'left' });
    const [beside] = settleLabels([{ x: 700, y: 30, align: 'left', width: 40 }], [strip], { bounds: { width: 1000, height: 700 } });
    expect(beside).toMatchObject({ x: 700, y: 30 });
  });

  it('keeps a label inside the view and off the colour bar at its foot', () => {
    const bounds = { width: 1440, height: 864 };
    // "72 N" past the view's foot: drawn whole, against it.
    const [cut] = settleLabels([{ x: 700, y: 862, align: 'center', width: 30 }], null, { bounds });
    expect(cut.y + 7).toBeLessThanOrEqual(864 - 4);
    // An arrow's label over the colour bar: lifted above it.
    const bar = { left: 560, top: 810, right: 880, bottom: 840 };
    const [lifted] = settleLabels([{ x: 700, y: 820, align: 'left', width: 40 }], [null, bar], { bounds });
    expect(lifted.y + 7).toBeLessThanOrEqual(810);
    expect(lifted.x).toBe(700);
  });

  it('reads the strip and the shown panels from the page, each its own box in the view\'s own pixels; nothing while they are put away', () => {
    document.body.innerHTML = `<div data-cad-scene-backdrop><div id="host"></div>
      <div data-cad-tool-groups><div id="strip"></div><div data-cad-tool-stack><section id="study" data-tool-panel="tree"></section>
      <section id="clip" data-tool-panel="fixed" hidden></section></div></div></div>`;
    const box = (id: string, left: number, top: number, width: number, height: number) => {
      document.getElementById(id)!.getBoundingClientRect = () => ({ left, top, right: left + width, bottom: top + height, width, height, x: left, y: top, toJSON() {} });
    };
    box('host', 0, 36, 1440, 864);
    box('strip', 8, 44, 60, 34);
    box('study', 8, 86, 164, 700);
    box('clip', 8, 790, 164, 60);
    const host = document.getElementById('host')!;
    // Each its own box: a label between the strip at the top and the panel at the left is under neither.
    expect(chromeCovers(host)).toEqual([{ left: 8, top: 8, right: 68, bottom: 42 }, { left: 8, top: 50, right: 172, bottom: 750 }]);
    // No colour bar: nothing at the foot.
    expect(colourBarCover(host)).toBeNull();
    expect(framingInset(host)).toEqual({ left: 172, bottom: 0 });
    const bar = document.createElement('div');
    bar.setAttribute('aria-label', 'Temperature colour bar');
    document.getElementById('host')!.append(bar);
    box('host', 0, 36, 1440, 864);
    bar.getBoundingClientRect = () => ({ left: 560, top: 846, right: 880, bottom: 876, width: 320, height: 30, x: 560, y: 846, toJSON() {} });
    expect(colourBarCover(host)).toEqual({ left: 560, top: 810, right: 880, bottom: 840 });
    // The camera frames above it, with a gap: 864 - 810 + 8.
    expect(framingInset(host)).toEqual({ left: 172, bottom: 62 });
    // The camera frames right of the panels: 172px of the view.
    expect(panelInset(host)).toBe(172);
    document.querySelector('[data-cad-tool-stack]')!.setAttribute('hidden', '');
    expect(chromeCovers(host)).toEqual([{ left: 8, top: 8, right: 68, bottom: 42 }]);
    // The strip alone covers only its corner: the camera takes the whole width.
    expect(panelInset(host)).toBe(0);
    expect(chromeCovers(document.createElement('div'))).toEqual([]);
  });
});
