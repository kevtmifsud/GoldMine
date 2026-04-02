import api from "./api";
import type {
  McpNamespace,
  McpTool,
  McpExecuteResult,
} from "../mocks/mcpMocks";
import {
  mockNamespaces,
  mockTools,
  mockExecuteResults,
} from "../mocks/mcpMocks";

export type { McpNamespace, McpTool, McpToolParameter, McpChartConfig, McpExecuteResult } from "../mocks/mcpMocks";

const useMock =
  import.meta.env.DEV && !import.meta.env.VITE_USE_REAL_MCP;

export async function fetchNamespaces(): Promise<McpNamespace[]> {
  if (useMock) return mockNamespaces;
  const res = await api.get<McpNamespace[]>("/api/mcp/namespaces");
  return res.data;
}

export async function fetchTools(namespace: string): Promise<McpTool[]> {
  if (useMock) return mockTools[namespace] ?? [];
  const res = await api.get<McpTool[]>("/api/mcp/tools", {
    params: { namespace },
  });
  return res.data;
}

export async function executeTool(
  toolFullName: string,
  params: Record<string, unknown>,
): Promise<McpExecuteResult> {
  if (useMock) {
    // Simulate network delay
    await new Promise((r) => setTimeout(r, 400));
    return (
      mockExecuteResults[toolFullName] ?? {
        rows: [],
        row_count: 0,
        columns: [],
        preferred_presentation: "table" as const,
        chart_config: null,
      }
    );
  }
  const res = await api.post<McpExecuteResult>("/api/mcp/execute", {
    tool: toolFullName,
    params,
  });
  return res.data;
}
