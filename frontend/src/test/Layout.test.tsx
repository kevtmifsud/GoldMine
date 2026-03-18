import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Layout } from "../components/Layout";

vi.mock("../auth/useAuth", () => ({
  useAuth: vi.fn(() => ({
    user: {
      username: "analyst1",
      display_name: "Test Analyst",
      role: "Research Analyst",
      email: "analyst1@test.com",
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  })),
}));

vi.mock("../components/SearchBar", () => ({
  SearchBar: () => <div data-testid="search-bar" />,
}));

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/packs"]}>
      <Layout>
        <div>Page Content</div>
      </Layout>
    </MemoryRouter>
  );
}

describe("Layout", () => {
  it("renders the logo", () => {
    renderLayout();
    expect(screen.getByText("GoldMine")).toBeInTheDocument();
  });

  it("renders nav links when user is logged in", () => {
    renderLayout();
    expect(screen.getByText("My Packs")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText("Portfolios")).toBeInTheDocument();
    expect(screen.getByText("Alerts")).toBeInTheDocument();
    expect(screen.getByText("Reports")).toBeInTheDocument();
  });

  it("renders user info and logout button", () => {
    renderLayout();
    expect(screen.getByText(/Test Analyst/)).toBeInTheDocument();
    expect(screen.getByText("Logout")).toBeInTheDocument();
  });

  it("calls logout when button is clicked", async () => {
    const { useAuth } = await import("../auth/useAuth");
    const mockLogout = vi.fn();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        username: "analyst1",
        display_name: "Test Analyst",
        role: "Research Analyst",
        email: "analyst1@test.com",
      },
      loading: false,
      login: vi.fn(),
      logout: mockLogout,
    });

    renderLayout();
    await userEvent.click(screen.getByText("Logout"));
    expect(mockLogout).toHaveBeenCalled();
  });

  it("renders children", () => {
    renderLayout();
    expect(screen.getByText("Page Content")).toBeInTheDocument();
  });
});
