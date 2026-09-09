export const noDynamicImportsRule = {
  meta: {
    type: 'problem',
    messages: {
      restricted:
        'Dynamic imports are not allowed. Use a static import and remove the side effect or cycle that required deferred loading.',
    },
  },
  create(context) {
    return {
      ImportExpression(node) {
        context.report({
          node,
          messageId: 'restricted',
        });
      },
    };
  },
};
