import type { ReactNode } from 'react';
import { projectSubject } from '@core/features/projects/contributions/subject';
import { SubjectProvider } from '@core/primitives/mementos/react';

interface ProjectViewWrapperProps {
  children: ReactNode;
  projectId: string;
}

export function ProjectViewWrapper({ children, projectId }: ProjectViewWrapperProps) {
  return <SubjectProvider subject={projectSubject({ projectId })}>{children}</SubjectProvider>;
}
