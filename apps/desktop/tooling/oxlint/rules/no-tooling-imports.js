const TOOLING_IMPORT_MESSAGE = '@tooling imports are only allowed in test files.';

function isToolingImport(value) {
  return value === '@tooling' || value.startsWith('@tooling/');
}

function sourceValue(node) {
  const source = node.source?.value;
  return typeof source === 'string' ? source : undefined;
}

function checkSource(context, node) {
  const source = sourceValue(node);
  if (!source || !isToolingImport(source)) return;

  context.report({
    node,
    messageId: 'restricted',
  });
}

export const noToolingImportsRule = {
  meta: {
    type: 'problem',
    messages: {
      restricted: TOOLING_IMPORT_MESSAGE,
    },
  },
  create(context) {
    return {
      ImportDeclaration(node) {
        checkSource(context, node);
      },
      ExportNamedDeclaration(node) {
        checkSource(context, node);
      },
      ExportAllDeclaration(node) {
        checkSource(context, node);
      },
    };
  },
};
