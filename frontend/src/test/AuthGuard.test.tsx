import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthGuard } from "../auth/AuthGuard";

const mockUseAuth = vi.fn();

vi.mock("../auth/useAuth", () => ({
  useAuth: (...args: unknown[]) => mockUseAuth(...args),
}));

function renderGuarded(initialPath = "/protected") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/protected"
          element={
            <AuthGuard>
              <div>Protected Content</div>
            </AuthGuard>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("AuthGuard", () => {
  it("renders children when authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: { username: "analyst1", display_name: "Analyst", role: "Research Analyst", email: "a@test.com" },
      loading: false,
    });

    renderGuarded();
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });

    renderGuarded();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });

  it("shows spinner while loading", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: true });

    const { container } = renderGuarded();
    expect(container.querySelector(".spinner")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });
});
