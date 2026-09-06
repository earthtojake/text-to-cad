// Type-resolution shim for the node program (mapped via `paths` in
// tsconfig.node.json). The real cross-fetch index.d.ts carries
// `/// <reference lib="dom" />`, which would drag the entire DOM lib into any
// program that resolves it — here via @emdash/plugins -> @mondaydotcomorg/api
// -> graphql-request -> cross-fetch. graphql-request only needs the shape of
// `fetch`, which @types/node already provides as an environment-neutral
// global, so redirect the module to these declarations instead.
declare const crossFetch: typeof globalThis.fetch;
declare const fetch: typeof globalThis.fetch;
declare const Request: typeof globalThis.Request;
declare const Response: typeof globalThis.Response;
declare const Headers: typeof globalThis.Headers;
export { fetch, Headers, Request, Response };
export default crossFetch;
