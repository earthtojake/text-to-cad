/** All possible states a file can be in once opened by the editor. */
export type ManagedFileKind =
  | 'text'
  | 'csv'
  | 'markdown'
  | 'html'
  | 'svg'
  | 'image'
  | 'pdf'
  | 'too-large'
  | 'binary';
