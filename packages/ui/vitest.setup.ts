// A host installs cadgen's display tessellation ladder before a STEP model is drawn (the web
// viewer from its server info, the CAD app from its launch). These tests draw as a host, with
// the ladder cadgen wrote for them (`@text-to-cad/core/lib/surf/fixtures/make_fixtures.py`).
import { installTestTessellationLadder } from '@text-to-cad/core/lib/surf/testing.js';

installTestTessellationLadder();
