import assert from "node:assert/strict";
import test from "node:test";

import {
  assertNoDeprecatedLocalRootEnv,
  normalizeViewerAssetBackend,
  vercelBlobCatalogUrlFromPrefix,
  vercelBlobConfigFromEnv,
  vercelBlobPrefixFromEnv,
  vercelBlobStoreIdFromEnv,
  VIEWER_ASSET_BACKENDS,
} from "./viewerEnv.mjs";

test("viewer env rejects deprecated local root environment variables", () => {
  assert.doesNotThrow(() => assertNoDeprecatedLocalRootEnv({}));
  assert.throws(
    () => assertNoDeprecatedLocalRootEnv({ VIEWER_LOCAL_ROOT_DIR: "models" }),
    /no longer supported/
  );
  assert.throws(
    () => assertNoDeprecatedLocalRootEnv({ VIEWER_LOCAL_WORKSPACE_ROOT: "/tmp/directory" }),
    /no longer supported/
  );
});

test("viewer env reads Blob settings", () => {
  assert.deepEqual(
    vercelBlobConfigFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "https://blob.example/models2/",
      VIEWER_VERCEL_BLOB_CATALOG_PATH: "catalog-0.1.3.json",
      VIEWER_VERCEL_BLOB_READ_WRITE_TOKEN: "test-token",
    }),
    {
      prefix: "https://blob.example/models2/",
      catalogPath: "catalog-0.1.3.json",
      catalogUrl: "https://blob.example/models2/catalog-0.1.3.json",
      token: "test-token",
    }
  );
  assert.equal(
    vercelBlobConfigFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "https://blob.example/models2/",
      BLOB_READ_WRITE_TOKEN: "blob-token",
    }).token,
    "blob-token"
  );
});

test("viewer env canonicalizes public Blob prefixes from BLOB_STORE_ID", () => {
  assert.equal(
    vercelBlobPrefixFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "https://TbC5QQRyTrzKn1QZ.public.blob.vercel-storage.com/models2",
      BLOB_STORE_ID: "store_TbC5QQRyTrzKnlQZ",
    }),
    "https://tbc5qqrytrzknlqz.public.blob.vercel-storage.com/models2"
  );
  assert.equal(
    vercelBlobConfigFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "https://TbC5QQRyTrzKn1QZ.public.blob.vercel-storage.com/models2",
      VIEWER_VERCEL_BLOB_CATALOG_PATH: "catalog-0.1.3.json",
      BLOB_STORE_ID: "store_TbC5QQRyTrzKnlQZ",
    }).catalogUrl,
    "https://tbc5qqrytrzknlqz.public.blob.vercel-storage.com/models2/catalog-0.1.3.json"
  );
});

test("viewer env can derive the Blob store ID from the server token", () => {
  assert.equal(
    vercelBlobStoreIdFromEnv({
      BLOB_READ_WRITE_TOKEN: "vercel_blob_rw_TbC5QQRyTrzKnlQZ_fakeSecret",
    }),
    "tbc5qqrytrzknlqz"
  );
  assert.equal(
    vercelBlobPrefixFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "https://TbC5QQRyTrzKn1QZ.public.blob.vercel-storage.com/models2",
      BLOB_READ_WRITE_TOKEN: "vercel_blob_rw_TbC5QQRyTrzKnlQZ_fakeSecret",
    }),
    "https://tbc5qqrytrzknlqz.public.blob.vercel-storage.com/models2"
  );
});

test("viewer env builds public Blob URLs from path-only prefixes and store IDs", () => {
  assert.equal(
    vercelBlobPrefixFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "models2",
      BLOB_STORE_ID: "store_TbC5QQRyTrzKnlQZ",
    }),
    "https://tbc5qqrytrzknlqz.public.blob.vercel-storage.com/models2"
  );
  assert.equal(
    vercelBlobConfigFromEnv({
      VIEWER_VERCEL_BLOB_PREFIX: "models2",
      VIEWER_VERCEL_BLOB_CATALOG_PATH: "catalog-0.1.3.json",
      BLOB_STORE_ID: "store_TbC5QQRyTrzKnlQZ",
    }).catalogUrl,
    "https://tbc5qqrytrzknlqz.public.blob.vercel-storage.com/models2/catalog-0.1.3.json"
  );
});

test("viewer env derives catalog URL only from public Blob URL prefixes", () => {
  assert.equal(
    vercelBlobCatalogUrlFromPrefix("https://blob.example/models2", "catalog-0.1.3.json"),
    "https://blob.example/models2/catalog-0.1.3.json"
  );
  assert.equal(vercelBlobCatalogUrlFromPrefix("models2"), "");
});

test("viewer env rejects unsupported asset backends", () => {
  assert.throws(
    () => normalizeViewerAssetBackend("s3"),
    /Unsupported VIEWER_ASSET_BACKEND/
  );
});
