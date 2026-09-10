import assert from 'node:assert/strict';
import test from 'node:test';
import { exportFilename, videoMimeType } from './reconstructionExport.js';
test('video formats follow actual encoder capabilities and do not relabel WebM as MP4', () => {
  assert.equal(videoMimeType({ isTypeSupported: t => t.startsWith('video/webm;codecs=vp8') }), 'video/webm;codecs=vp8');
  assert.equal(videoMimeType({ isTypeSupported: () => false }), null);
  assert.equal(videoMimeType({ isTypeSupported: () => true }), 'video/mp4;codecs=avc1.42001E');
});
test('export filenames stay one safe filename with the correct media extension', () => {
  assert.equal(exportFilename('part/left:*', 'gif'), 'part-left---build-sequence.gif');
  assert.equal(exportFilename('', 'mp4'), 'Part-build-sequence.mp4');
});
