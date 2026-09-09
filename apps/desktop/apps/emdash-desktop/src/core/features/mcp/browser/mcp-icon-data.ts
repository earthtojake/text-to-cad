export function coerceRawSvgContent(payload: unknown): string | undefined {
  if (typeof payload === 'string') {
    return payload;
  }

  if (
    payload &&
    typeof payload === 'object' &&
    'default' in payload &&
    typeof payload.default === 'string'
  ) {
    return payload.default;
  }

  return undefined;
}

function hasExplicitSvgColors(svgContent: string): boolean {
  return (
    /\bfill\s*=\s*"(?!none|currentColor)[^"]+"/i.test(svgContent) ||
    /\bstroke\s*=\s*"(?!none|currentColor)[^"]+"/i.test(svgContent) ||
    /\bfill\s*:\s*(?!none|currentColor)[^;}"'\s]+/i.test(svgContent) ||
    /\bstop-color\s*=/i.test(svgContent) ||
    /url\s*\(\s*#/i.test(svgContent)
  );
}

function stripRootSvgDimensions(svgContent: string): string {
  return svgContent.replace(/<svg\b([^>]*)>/, (_match, attributes: string) => {
    const withoutDimensions = attributes
      .replace(/\swidth="[^"]*"/g, '')
      .replace(/\sheight="[^"]*"/g, '');

    return `<svg${withoutDimensions}>`;
  });
}

function shouldApplyRootCurrentColorFill(svgContent: string): boolean {
  if (hasExplicitSvgColors(svgContent)) {
    return false;
  }

  if (/<svg\b[^>]*\bfill\s*=\s*"none"/i.test(svgContent)) {
    return false;
  }

  const hasFilledPaths = /<path\b[^>]*\bfill\s*=\s*"(?!none|currentColor)[^"]*"/i.test(svgContent);
  const hasStrokePaths = /<path\b[^>]*\bstroke\s*=/i.test(svgContent);

  if (hasStrokePaths && !hasFilledPaths) {
    return false;
  }

  return true;
}

export function prepareInlineSvgMarkup(svgContent: string): string {
  const withoutDimensions = stripRootSvgDimensions(svgContent);
  const svgAttributes = shouldApplyRootCurrentColorFill(withoutDimensions)
    ? 'fill="currentColor" class="h-full w-full"'
    : 'class="h-full w-full"';

  return withoutDimensions.replace('<svg ', `<svg ${svgAttributes} `);
}
