import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import SdfSection from '../../../dist/renderers/robot/SdfSection.js';
import { ViewerMobileContext } from '../../../dist/file-viewer/responsive.js';
import { fixturePayload } from './__tests__/robotFixtures.js';

afterEach(cleanup);

// What an SDF says of itself beyond its links and joints, from cadgen's answer for `swing.sdf` (the
// robot renderer shows it as the sidebar's SDF section). The ground plane under its base is a
// collision the viewer cannot draw: counted, never refused.
it("an SDF's section says its document, its counts and its lights, and counts the geometry the viewer cannot draw", () => {
  const { container } = render(<SdfSection info={fixturePayload('swing.sdf').sdf} />);
  const text = container.textContent!.replace(/\s+/g, '');  // each label runs into its value
  for (const fact of ['Version1.9', 'Documentworld', 'Worldlab', 'Rootlinkbase', 'Modelswing', 'Links2', 'Joints1', 'Lights1',
    'Unsupportedgeom.1', 'sun/directional']) expect(text).toContain(fact);
});

// The counts are three tiles a row on a desktop; on a phone (a 288px panel, type a step larger) two,
// in the same order, so the long labels read whole.
it("lays the counts out three a row, and two on a phone, in one order", () => {
  const columns = (mobile: boolean) => {
    const { container } = render(<ViewerMobileContext.Provider value={mobile}><SdfSection info={fixturePayload('swing.sdf').sdf} /></ViewerMobileContext.Provider>);
    const grid = container.querySelector('[data-sdf-counts]') as HTMLElement;
    const labels = [...grid.children].map(tile => tile.querySelector('span')?.textContent);
    cleanup();
    return [grid.style.gridTemplateColumns, labels] as const;
  };
  const [desktop, order] = columns(false);
  const [phone, phoneOrder] = columns(true);
  expect([desktop, phone]).toEqual(['repeat(3, minmax(0, 1fr))', 'repeat(2, minmax(0, 1fr))']);
  expect(order.slice(0, 3)).toEqual(['Links', 'Joints', 'Frames']);
  expect(phoneOrder).toEqual(order);
});
