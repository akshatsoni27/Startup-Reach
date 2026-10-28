import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { State } from "./components";

describe("shared UI states", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(<State loading />);
    expect(container.querySelector(".skeleton")).toBeTruthy();
  });

  it("renders a useful empty state", () => {
    render(<State empty="No companies discovered yet." />);
    expect(screen.getByText("No companies discovered yet.")).toBeInTheDocument();
    expect(screen.getByText(/Connect your backend/)).toBeInTheDocument();
  });

  it("renders an error without exposing implementation details", () => {
    render(<State error="Authentication required." />);
    expect(screen.getByText("Authentication required.")).toBeInTheDocument();
  });
});
