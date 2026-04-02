import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SlashMenu } from "../components/chat/SlashMenu";
import { mockTools } from "../mocks/mcpMocks";
import type { SlashCommandState, SlashCommandActions } from "../hooks/useSlashCommand";

function buildSlash(
  overrides: Partial<SlashCommandState & SlashCommandActions> = {},
): SlashCommandState & SlashCommandActions {
  return {
    slashMode: true,
    slashMenuVisible: true,
    menuMode: "categories",
    slashCategory: null,
    slashToolName: null,
    slashParams: [],
    currentParamIndex: 0,
    allTools: [...mockTools.estimates, ...mockTools.altdata],
    categoryTools: [],
    selectedTool: null,
    loading: false,
    selectedIndex: 0,
    requiredParamsFilled: false,
    firstMissingRequired: 0,
    parseInput: vi.fn(),
    selectCategory: vi.fn(() => "/estimates "),
    selectTool: vi.fn(() => "/estimates get_estimates "),
    selectEnumValue: vi.fn(() => "/estimates get_estimates AAPL diluted_eps "),
    dismissMenu: vi.fn(),
    setSelectedIndex: vi.fn(),
    autocomplete: vi.fn(() => null),
    menuItemCount: vi.fn(() => 6),
    ...overrides,
  };
}

function renderMenu(
  slashOverrides: Partial<SlashCommandState & SlashCommandActions> = {},
  props: Partial<{
    onSelectCategory: (slug: string) => void;
    onSelectTool: (toolName: string) => void;
    onSelectEnumValue: (value: string) => void;
    onSendPrompt: (prompt: string) => void;
    onDismiss: () => void;
  }> = {},
) {
  const slash = buildSlash(slashOverrides);
  const defaultProps = {
    slash,
    onSelectCategory: vi.fn(),
    onSelectTool: vi.fn(),
    onSelectEnumValue: vi.fn(),
    onSendPrompt: vi.fn(),
    onDismiss: vi.fn(),
    ...props,
  };
  const result = render(<SlashMenu {...defaultProps} />);
  return { ...result, ...defaultProps };
}

describe("SlashMenu", () => {
  describe("Category picker", () => {
    it("renders categories that have available tools", () => {
      // Mock allTools only has get_estimates (Estimates) and get_alt_data (Alt Data)
      renderMenu();
      expect(screen.getByText("Estimates")).toBeInTheDocument();
      expect(screen.getByText("Alt Data")).toBeInTheDocument();
      // Categories with no loaded tools should be hidden
      expect(screen.queryByText("Portfolio")).not.toBeInTheDocument();
      expect(screen.queryByText("Workflows")).not.toBeInTheDocument();
    });

    it("shows 'Commands' header", () => {
      renderMenu();
      expect(screen.getByText("Commands")).toBeInTheDocument();
    });

    it("calls onSelectCategory when clicked", async () => {
      const user = userEvent.setup();
      const { onSelectCategory } = renderMenu();
      await user.click(screen.getByText("Estimates"));
      expect(onSelectCategory).toHaveBeenCalledWith("estimates");
    });

    it("filters categories on partial input", () => {
      renderMenu({ slashCategory: "alt" });
      expect(screen.getByText("Alt Data")).toBeInTheDocument();
      expect(screen.queryByText("Estimates")).not.toBeInTheDocument();
    });

    it("shows no match message for invalid input", () => {
      renderMenu({ slashCategory: "xyz" });
      expect(screen.getByText("No matching categories")).toBeInTheDocument();
    });
  });

  describe("Tool list", () => {
    it("renders tools for selected category", () => {
      renderMenu({
        menuMode: "tools",
        slashCategory: "altdata",
        categoryTools: [...mockTools.estimates, ...mockTools.altdata].filter((t) => t.name === "get_alt_data"),
      });
      expect(screen.getByText("get_alt_data")).toBeInTheDocument();
    });

    it("shows category name in header", () => {
      renderMenu({
        menuMode: "tools",
        slashCategory: "estimates",
        categoryTools: [...mockTools.estimates, ...mockTools.altdata].filter((t) => t.name === "get_estimates"),
      });
      expect(screen.getByText("Estimates")).toBeInTheDocument();
    });

    it("calls onSelectTool when clicked", async () => {
      const user = userEvent.setup();
      const { onSelectTool } = renderMenu({
        menuMode: "tools",
        slashCategory: "estimates",
        categoryTools: [...mockTools.estimates, ...mockTools.altdata].filter((t) => t.name === "get_estimates"),
      });
      await user.click(screen.getByText("get_estimates"));
      expect(onSelectTool).toHaveBeenCalledWith("get_estimates");
    });

    it("shows required param hints", () => {
      renderMenu({
        menuMode: "tools",
        slashCategory: "estimates",
        categoryTools: [...mockTools.estimates, ...mockTools.altdata].filter((t) => t.name === "get_estimates"),
      });
      expect(screen.getByText("<ticker> <metric>")).toBeInTheDocument();
    });
  });

  describe("Inline param hints", () => {
    const paramSlash = {
      menuMode: "params" as const,
      slashCategory: "estimates",
      slashToolName: "get_estimates",
      selectedTool: mockTools.estimates[0],
      slashParams: ["AAPL"],
      currentParamIndex: 1,
    };

    it("shows function signature with current param highlighted", () => {
      const { container } = renderMenu(paramSlash);
      // Should show the function name
      expect(screen.getAllByText(/get_estimates/).length).toBeGreaterThan(0);
      // Current param (metric) should have active class
      const active = container.querySelector(".slash-param-sig__param--active");
      expect(active).not.toBeNull();
      expect(active?.textContent).toContain("metric");
    });

    it("shows filled params", () => {
      const { container } = renderMenu(paramSlash);
      const filled = container.querySelector(".slash-param-sig__param--filled");
      expect(filled).not.toBeNull();
      expect(filled?.textContent).toContain("AAPL");
    });

    it("shows enum options for current param", () => {
      renderMenu(paramSlash);
      expect(screen.getByText("total_revenue")).toBeInTheDocument();
      expect(screen.getByText("diluted_eps")).toBeInTheDocument();
      expect(screen.getByText("ebitda")).toBeInTheDocument();
    });

    it("calls onSelectEnumValue when enum chip clicked", async () => {
      const user = userEvent.setup();
      const { onSelectEnumValue } = renderMenu(paramSlash);
      await user.click(screen.getByText("diluted_eps"));
      expect(onSelectEnumValue).toHaveBeenCalledWith("diluted_eps");
    });

    it("shows param description", () => {
      renderMenu(paramSlash);
      expect(screen.getByText("Metric to retrieve")).toBeInTheDocument();
    });
  });

  describe("Dismiss", () => {
    it("calls onDismiss when Esc clicked", async () => {
      const user = userEvent.setup();
      const { onDismiss } = renderMenu();
      await user.click(screen.getByText("Esc"));
      expect(onDismiss).toHaveBeenCalled();
    });
  });

  describe("Keyboard navigation", () => {
    it("highlights category at selectedIndex", () => {
      // With mock tools, visible categories are: Estimates (idx 0), Alt Data (idx 1)
      const { container } = renderMenu({ selectedIndex: 1 });
      const selected = container.querySelector(".slash-menu__item--selected");
      expect(selected).not.toBeNull();
      expect(selected?.textContent).toContain("Alt Data");
    });

    it("highlights enum option at selectedIndex in params mode", () => {
      const { container } = renderMenu({
        menuMode: "params",
        slashCategory: "estimates",
        slashToolName: "get_estimates",
        selectedTool: mockTools.estimates[0],
        slashParams: ["AAPL"],
        currentParamIndex: 1,
        selectedIndex: 2,
      });
      const selected = container.querySelector(".slash-param-enum__item--selected");
      expect(selected).not.toBeNull();
      expect(selected?.textContent).toBe("ebitda");
    });
  });
});
