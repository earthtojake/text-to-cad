import { describe, expect, it } from 'vitest';
import { projectPanelLayoutsMemento } from '@core/features/projects/contributions/mementos';
import { taskPanelLayoutsMemento } from '@core/features/tasks/contributions/mementos';
import { mementoCatalog } from './memento-catalog';

describe('mementoCatalog', () => {
  it('registers the task- and project-scoped panel-layouts mementos', () => {
    expect(taskPanelLayoutsMemento.id).toBe('tasks.panel-layouts');
    expect(taskPanelLayoutsMemento.subject.kind).toBe('task');
    expect(taskPanelLayoutsMemento.retention.tier).toBe('persisted');
    expect(projectPanelLayoutsMemento.id).toBe('projects.panel-layouts');
    expect(projectPanelLayoutsMemento.subject.kind).toBe('project');
    expect(projectPanelLayoutsMemento.retention.tier).toBe('persisted');

    expect(mementoCatalog).toContain(taskPanelLayoutsMemento);
    expect(mementoCatalog).toContain(projectPanelLayoutsMemento);
  });

  it('round-trips panel-layouts values through their versioned schemas', () => {
    const value = {
      version: '1' as const,
      layouts: { 'react-resizable-panels:task-sidebar-split': '{"sidebar":30,"main":70}' },
    };
    for (const definition of [taskPanelLayoutsMemento, projectPanelLayoutsMemento]) {
      expect(definition.schema.parseJson(definition.schema.serialize(value))).toEqual(value);
      expect(definition.default).toEqual({ version: '1', layouts: {} });
    }
  });
});
