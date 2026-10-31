
/** @type {readonly ShapeTool[]} */
export const SHAPE_TOOLS = Object.freeze(['rectangle', 'line', 'arrow', 'ellipse', 'text']);
/** The tool each strip tool takes up first. */
export const DEFAULT_PENCIL_TOOL = 'freedraw';
export const DEFAULT_SHAPE_TOOL = 'rectangle';

/** The strip tool a drawing tool belongs to. */
export const toolFamily = tool => (SHAPE_TOOLS.includes(tool) ? 'shapes' : 'pencil');

/**
 * The style slot a drawing tool puts ink down with (`session.js`): the pen, the highlighter, or Shapes (all five
 * shapes share one). The eraser puts nothing down and has none: `null`.
 * @typedef {'pen' | 'highlighter' | 'shapes'} StyleSlot
 * @param {AnnotationTool} tool
 * @returns {StyleSlot | null}
 */
export const styleSlot = tool => (tool === 'eraser' ? null : tool === 'highlighter' ? 'highlighter' : SHAPE_TOOLS.includes(tool) ? 'shapes' : 'pen');
