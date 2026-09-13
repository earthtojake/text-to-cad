import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import React from 'react';
import { McpPanel } from '@core/features/mcp/contributions/browser/McpPanel';

export const McpView: React.FC = () => (
  <McpPanel
    host={LOCAL_HOST_REF}
    header={{
      title: 'MCP',
      description: 'Connect your agents with external data sources and tools',
    }}
  />
);
