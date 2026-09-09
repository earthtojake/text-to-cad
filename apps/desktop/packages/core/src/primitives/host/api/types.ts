export type HostType = 'local' | 'remote';

/** Logical routing identity for a runtime host. */
export type HostRef = Readonly<{
  type: HostType;
  id: string;
}>;

/** Canonical durable/wire encoding produced by `formatHostRef`. */
export type SerializedHostRef = string & {
  readonly __serializedHostRef: 'SerializedHostRef';
};
