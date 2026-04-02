import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchNamespaces,
  fetchTools,
  type McpNamespace,
  type McpTool,
} from "../config/mcpApi";

/**
 * Tool categories — the first-level menu when "/" is typed.
 * Maps category slug (typed in input) → display name + tool names.
 */
export const TOOL_CATEGORIES: Record<
  string,
  { display: string; description: string; tools: string[] }
> = {
  estimates: {
    display: "Estimates",
    description: "Forward estimates from all sources — consensus, buyside, internal, sellside",
    tools: ["get_estimates", "get_estimate_history"],
  },
  portfolio: {
    display: "Portfolio",
    description: "P&L, concentration, risk exposures, and trade requests",
    tools: ["get_daily_pnl", "get_pnl_history", "get_portfolio_concentration", "get_portfolio_risk", "get_trade_requests"],
  },
  financials: {
    display: "Financials",
    description: "Income statement, balance sheet, cash flow, stock prices, guidance",
    tools: ["get_financial_metrics", "get_stock_history", "get_guidance"],
  },
  altdata: {
    display: "Alt Data",
    description: "Credit card, foot traffic, app downloads, web traffic, job postings",
    tools: ["get_alt_data", "list_alt_data"],
  },
  research: {
    display: "Research",
    description: "Search transcripts, filings, analyst notes, and stock universe",
    tools: ["search_documents", "search_universe"],
  },
  workflows: {
    display: "Workflows",
    description: "Run workflows, view outputs, edit models",
    tools: ["run_workflow", "get_workflow_output", "get_workflow_registry", "get_model_outputs", "model_edit"],
  },
};

export const CATEGORY_SLUGS = Object.keys(TOOL_CATEGORIES);

/** Look up the category slug for a tool name. Returns "other" if not found. */
export function toolCategorySlug(toolName: string): string {
  for (const [slug, cat] of Object.entries(TOOL_CATEGORIES)) {
    if (cat.tools.includes(toolName)) return slug;
  }
  return "other";
}

// ── Slash menu mode ──
// "categories" = showing category list
// "tools"      = showing tools within a category
// "params"     = tool selected, typing params inline
type SlashMenuMode = "categories" | "tools" | "params";

export interface SlashCommandState {
  slashMode: boolean;
  slashMenuVisible: boolean;
  menuMode: SlashMenuMode;
  slashCategory: string | null;       // e.g. "estimates"
  slashToolName: string | null;       // e.g. "get_estimates"
  slashParams: string[];              // e.g. ["AAPL", "diluted_eps"]
  currentParamIndex: number;          // which param is being typed
  allTools: McpTool[];                // all tools from backend
  categoryTools: McpTool[];           // tools filtered to current category
  selectedTool: McpTool | null;       // resolved tool object
  loading: boolean;
  selectedIndex: number;
  /** True when every required parameter has a non-empty value. */
  requiredParamsFilled: boolean;
  /** Index of the first required param that is still empty, or -1 if all filled. */
  firstMissingRequired: number;
}

export interface SlashCommandActions {
  parseInput: (value: string) => void;
  selectCategory: (slug: string) => string;
  selectTool: (toolName: string) => string;
  selectEnumValue: (value: string) => string;
  dismissMenu: () => void;
  setSelectedIndex: (index: number) => void;
  autocomplete: (currentInput: string) => string | null;
  menuItemCount: () => number;
}

export function useSlashCommand(): SlashCommandState & SlashCommandActions {
  const [slashMode, setSlashMode] = useState(false);
  const [slashMenuVisible, setSlashMenuVisible] = useState(false);
  const [menuMode, setMenuMode] = useState<SlashMenuMode>("categories");
  const [slashCategory, setSlashCategory] = useState<string | null>(null);
  const [slashToolName, setSlashToolName] = useState<string | null>(null);
  const [slashParams, setSlashParams] = useState<string[]>([]);
  const [currentParamIndex, setCurrentParamIndex] = useState(0);
  const [allTools, setAllTools] = useState<McpTool[]>([]);
  const [categoryTools, setCategoryTools] = useState<McpTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const toolsCacheRef = useRef<McpTool[] | null>(null);

  // Load all tools from all namespaces on first "/" press
  const loadAllTools = useCallback(async () => {
    if (toolsCacheRef.current) {
      setAllTools(toolsCacheRef.current);
      return;
    }
    setLoading(true);
    try {
      const nsList = await fetchNamespaces();
      const toolLists = await Promise.all(
        nsList.map((ns: McpNamespace) => fetchTools(ns.namespace)),
      );
      const all = toolLists.flat();
      toolsCacheRef.current = all;
      setAllTools(all);
    } catch {
      setAllTools([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Derive selectedTool
  const selectedTool =
    slashToolName && allTools.length > 0
      ? allTools.find((t) => t.name === slashToolName) ?? null
      : null;

  // Reserved direct commands — bypass slash menu entirely
  const RESERVED_COMMANDS = new Set(["/pack"]);

  // Parse input on every keystroke
  const parseInput = useCallback(
    (value: string) => {
      const trimmed = value.trim().toLowerCase();
      const firstWord = trimmed.split(" ")[0];

      // Not a slash command, or is a reserved command — no menu
      if (!value.startsWith("/") || RESERVED_COMMANDS.has(firstWord)) {
        setSlashMode(false);
        setSlashMenuVisible(false);
        setMenuMode("categories");
        setSlashCategory(null);
        setSlashToolName(null);
        setSlashParams([]);
        setCurrentParamIndex(0);
        setSelectedIndex(0);
        return;
      }

      setSlashMode(true);
      setSlashMenuVisible(true);
      loadAllTools();

      const rest = value.slice(1);
      const parts = rest.split(/\s+/);
      const catCandidate = parts[0] ?? "";
      const toolCandidate = parts.length > 1 ? parts[1] : null;
      // Filter empty strings — trailing spaces produce "" from split
      const paramParts = parts.length > 2
        ? parts.slice(2).filter(Boolean)
        : [];

      const hasSpaceAfterCat =
        rest.length > catCandidate.length && rest[catCandidate.length] === " ";

      if (!hasSpaceAfterCat) {
        // Still typing category
        setMenuMode("categories");
        setSlashCategory(catCandidate || null);
        setSlashToolName(null);
        setSlashParams([]);
        setCurrentParamIndex(0);
      } else {
        // Category selected
        setSlashCategory(catCandidate);

        // Filter tools to this category
        const catDef = TOOL_CATEGORIES[catCandidate];
        if (catDef) {
          const filtered = allTools.filter((t) => catDef.tools.includes(t.name));
          setCategoryTools(filtered);
        } else {
          setCategoryTools(allTools);
        }

        if (!toolCandidate || toolCandidate === "") {
          // Show tool list
          setMenuMode("tools");
          setSlashToolName(null);
          setSlashParams([]);
          setCurrentParamIndex(0);
        } else {
          const hasSpaceAfterTool =
            rest.length > catCandidate.length + 1 + toolCandidate.length &&
            rest[catCandidate.length + 1 + toolCandidate.length] === " ";

          if (!hasSpaceAfterTool) {
            // Still typing tool name
            setMenuMode("tools");
            setSlashToolName(toolCandidate);
            setSlashParams([]);
            setCurrentParamIndex(0);
          } else {
            // Tool selected, in param mode
            setMenuMode("params");
            setSlashToolName(toolCandidate);
            setSlashParams(paramParts);
            // Current param index = number of completed params
            // If the input ends with a space, user is starting a new param
            const endsWithSpace = value.endsWith(" ");
            setCurrentParamIndex(
              endsWithSpace ? paramParts.length : Math.max(0, paramParts.length - 1),
            );
          }
        }
      }
    },
    [loadAllTools, allTools],
  );

  // Reset selected index when menu content changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [menuMode, slashCategory, slashToolName]);

  const selectCategory = useCallback((slug: string): string => {
    setSlashCategory(slug);
    setMenuMode("tools");
    setSelectedIndex(0);
    return `/${slug} `;
  }, []);

  const selectTool = useCallback(
    (toolName: string): string => {
      setSlashToolName(toolName);
      setMenuMode("params");
      setSlashParams([]);
      setCurrentParamIndex(0);
      setSelectedIndex(0);
      return `/${slashCategory} ${toolName} `;
    },
    [slashCategory],
  );

  const selectEnumValue = useCallback(
    (value: string): string => {
      // Build a clean params array up to currentParamIndex, then set the value
      const newParams: string[] = [];
      for (let i = 0; i <= currentParamIndex; i++) {
        newParams[i] = i === currentParamIndex ? value : (slashParams[i] ?? "");
      }
      setSlashParams(newParams.filter(Boolean));
      return `/${slashCategory} ${slashToolName} ${newParams.filter(Boolean).join(" ")} `;
    },
    [slashCategory, slashToolName, slashParams, currentParamIndex],
  );

  const dismissMenu = useCallback(() => {
    setSlashMenuVisible(false);
    setSlashMode(false);
    setMenuMode("categories");
    setSlashCategory(null);
    setSlashToolName(null);
    setSlashParams([]);
    setCurrentParamIndex(0);
    setSelectedIndex(0);
  }, []);

  const menuItemCount = useCallback((): number => {
    if (!slashMode) return 0;

    if (menuMode === "categories") {
      const partial = slashCategory?.toLowerCase() ?? "";
      return CATEGORY_SLUGS.filter((s) => {
        if (!s.startsWith(partial)) return false;
        // Only count categories that have actual tools loaded
        const cat = TOOL_CATEGORIES[s];
        return cat.tools.some((n) => allTools.some((t) => t.name === n));
      }).length;
    }

    if (menuMode === "tools") {
      const partial = slashToolName?.toLowerCase() ?? "";
      return categoryTools.filter((t) =>
        t.name.toLowerCase().startsWith(partial),
      ).length;
    }

    if (menuMode === "params" && selectedTool) {
      const param = selectedTool.parameters[currentParamIndex];
      if (param?.enum) return param.enum.length;
    }

    return 0;
  }, [slashMode, menuMode, slashCategory, slashToolName, categoryTools, selectedTool, currentParamIndex, allTools]);

  const autocomplete = useCallback(
    (currentInput: string): string | null => {
      if (!slashMode || !currentInput.startsWith("/")) return null;

      const rest = currentInput.slice(1);
      const parts = rest.split(/\s+/);
      const catCandidate = parts[0] ?? "";
      const hasSpaceAfterCat =
        rest.length > catCandidate.length && rest[catCandidate.length] === " ";

      if (!hasSpaceAfterCat) {
        // Autocomplete category
        const match = CATEGORY_SLUGS.find((s) =>
          s.startsWith(catCandidate.toLowerCase()),
        );
        if (match) return `/${match} `;
      } else {
        // Autocomplete tool
        const toolCandidate = parts[1] ?? "";
        const match = categoryTools.find((t) =>
          t.name.toLowerCase().startsWith(toolCandidate.toLowerCase()),
        );
        if (match) return `/${catCandidate} ${match.name} `;
      }
      return null;
    },
    [slashMode, categoryTools],
  );

  // Derived: check if all required params have values
  let requiredParamsFilled = true;
  let firstMissingRequired = -1;
  if (selectedTool) {
    for (let i = 0; i < selectedTool.parameters.length; i++) {
      const p = selectedTool.parameters[i];
      if (p.required && !(slashParams[i] ?? "").trim()) {
        requiredParamsFilled = false;
        if (firstMissingRequired === -1) firstMissingRequired = i;
      }
    }
  }

  return {
    slashMode,
    slashMenuVisible,
    menuMode,
    slashCategory,
    slashToolName,
    slashParams,
    currentParamIndex,
    allTools,
    categoryTools,
    selectedTool,
    loading,
    selectedIndex,
    requiredParamsFilled,
    firstMissingRequired,
    parseInput,
    selectCategory,
    selectTool,
    selectEnumValue,
    dismissMenu,
    setSelectedIndex,
    autocomplete,
    menuItemCount,
  };
}
