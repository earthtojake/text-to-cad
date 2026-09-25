import type { ComponentType } from 'react';
import type { FileRendererProps, RendererViewProps } from '../../file-viewer/types.js';
import type { PreparedStepDocument } from './index.js';
import StepSurface from './StepSurface.jsx';

const Surface = StepSurface as ComponentType<{ view: RendererViewProps; data: PreparedStepDocument }>;

/** Like every renderer on the shell: the host's view props as they came, and the prepared document. */
export default function StepRenderer(props: FileRendererProps<PreparedStepDocument>) {
  const { data, ...view } = props;
  return <Surface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
