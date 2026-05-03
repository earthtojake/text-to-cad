import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCadProjectPackage,
  buildCadProjectPackageSummary,
  buildEntryDownloadUrl,
  buildOttoAuthCartReturnUrl,
  buildOttoAuthConnectUrl,
  buildOttoAuthLoginUrl,
  buildOttoAuthOrderUrl,
  buildOttoAuthTaskPayload,
  entryFormatLabel,
  parseUsdToCents
} from "./ottoAuth.js";

test("buildEntryDownloadUrl resolves STEP sources relative to the explorer root", () => {
  const entry = {
    kind: "part",
    name: "mount.step",
    step: { path: "parts/mount.step" }
  };

  assert.equal(
    buildEntryDownloadUrl(entry, {
      origin: "http://127.0.0.1:4178",
      catalogRootDir: "fixtures"
    }),
    "http://127.0.0.1:4178/fixtures/parts/mount.step"
  );
});

test("buildEntryDownloadUrl prefers served asset URLs for mesh formats", () => {
  const entry = {
    kind: "stl",
    name: "clip.stl",
    assets: {
      stl: {
        url: "/exports/clip.stl?v=abc"
      }
    }
  };

  assert.equal(
    buildEntryDownloadUrl(entry, { origin: "http://localhost:4178" }),
    "http://localhost:4178/exports/clip.stl?v=abc"
  );
  assert.equal(entryFormatLabel(entry), "STL");
});

test("buildOttoAuthTaskPayload includes CAD context and optional spend cap", () => {
  const payload = buildOttoAuthTaskPayload({
    entry: {
      kind: "assembly",
      name: "gantry.step"
    },
    sourceUrl: "http://localhost:4178/gantry.step",
    form: {
      quantity: "2",
      material: "6061 aluminum, black anodized",
      packageSummary: "CAD project package:\nSelected CAD file: gantry.step",
      supplierName: "Xometry",
      supplierUrl: "https://www.xometry.com/",
      maxSpendUsd: "$125.50"
    }
  });

  assert.equal(payload.task_title, "Buy parts: gantry.step");
  assert.equal(payload.app_id, "cad-explorer");
  assert.equal(payload.kind, "buy_parts");
  assert.equal(payload.merchant_name, "Xometry");
  assert.equal(payload.url_policy, "preferred");
  assert.equal(payload.url, "https://www.xometry.com/");
  assert.equal(payload.max_charge_cents, 12550);
  assert.equal(payload.fulfillment_mode, undefined);
  assert.match(payload.task, /Selected CAD file: gantry\.step \(STEP\)/);
  assert.match(payload.task, /CAD project package:\nSelected CAD file: gantry\.step/);
  assert.match(payload.task, /CAD source URL: http:\/\/localhost:4178\/gantry\.step/);
});

test("buildCadProjectPackage summarizes project CAD files and selected assembly parts", () => {
  const selectedEntry = {
    file: "assembly/fixture.step",
    kind: "assembly",
    name: "fixture.step",
    step: { path: "assembly/fixture.step" }
  };
  const cadPackage = buildCadProjectPackage({
    selectedEntry,
    entries: [
      selectedEntry,
      {
        file: "parts/bracket.stl",
        kind: "stl",
        name: "bracket.stl",
        assets: { stl: { url: "/parts/bracket.stl?v=abc" } }
      }
    ],
    assemblyParts: [
      { id: "a", name: "left bracket", sourcePath: "parts/left.step" },
      { id: "b", name: "right bracket", sourcePath: "parts/right.step" }
    ],
    selectedPartIds: ["b"],
    origin: "http://127.0.0.1:4178",
    catalogRootDir: "project"
  });
  const summary = buildCadProjectPackageSummary(cadPackage);

  assert.equal(cadPackage.cadFiles.length, 2);
  assert.equal(cadPackage.parts.length, 1);
  assert.equal(cadPackage.parts[0].label, "right bracket");
  assert.equal(cadPackage.primarySourceUrl, "http://127.0.0.1:4178/project/assembly/fixture.step");
  assert.match(summary, /Project CAD files \(2\):/);
  assert.match(summary, /Assembly parts \(1, 1 selected\):/);
  assert.match(summary, /right bracket/);
});

test("parseUsdToCents accepts formatted dollars", () => {
  assert.equal(parseUsdToCents("19.99"), 1999);
  assert.equal(parseUsdToCents("$1,250.45"), 125045);
  assert.equal(parseUsdToCents(""), null);
  assert.equal(parseUsdToCents("free"), null);
});

test("buildOttoAuthOrderUrl points to a task when one is available", () => {
  assert.equal(
    buildOttoAuthOrderUrl("http://localhost:3000/", "task 42"),
    "http://localhost:3000/orders/task%2042"
  );
  assert.equal(
    buildOttoAuthOrderUrl("http://localhost:3000/"),
    "http://localhost:3000/orders/new"
  );
});

test("buildOttoAuthConnectUrl points at the OttoAuth SDK connect route", () => {
  const loginUrl = new URL(buildOttoAuthConnectUrl(
    "http://127.0.0.1:3000/",
    "http://127.0.0.1:4178/?ottoauthCart=1"
  ));
  assert.equal(loginUrl.origin, "http://127.0.0.1:3000");
  assert.equal(loginUrl.pathname, "/api/sdk/connect");
  assert.equal(loginUrl.searchParams.get("app_id"), "cad-explorer");
  assert.equal(loginUrl.searchParams.get("app_name"), "CAD Explorer");
  assert.equal(
    loginUrl.searchParams.get("return_to"),
    "http://127.0.0.1:4178/?ottoauthCart=1"
  );
  assert.equal(buildOttoAuthLoginUrl(
    "http://127.0.0.1:3000/",
    "http://127.0.0.1:4178/?ottoauthCart=1"
  ), loginUrl.href);
});

test("buildOttoAuthCartReturnUrl marks the explorer URL to reopen the cart", () => {
  assert.equal(
    buildOttoAuthCartReturnUrl("http://127.0.0.1:4178/?file=parts%2Fbracket.step"),
    "http://127.0.0.1:4178/?file=parts%2Fbracket.step&ottoauthCart=1"
  );
});
