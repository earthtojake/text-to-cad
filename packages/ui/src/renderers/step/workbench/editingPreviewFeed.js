export function observeEditingPreview(file, onUpdate, onError, { client, ...options } = {}) {
  if (!client?.observeEditingPreview) throw new TypeError("Editing preview requires a CAD workspace service");
  return client.observeEditingPreview(file, onUpdate, onError, options);
}
