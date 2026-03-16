import { screen } from "@testing-library/react";
import { renderWithProviders } from "../helpers";

const mockProofJobs = jest.fn();

jest.mock("@/lib/api", () => ({
  useProofJobs: () => mockProofJobs(),
}));

jest.mock("next/link", () => {
  return function MockLink({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    );
  };
});

import ProofsPage from "@/app/proofs/page";

describe("ProofsPage", () => {
  beforeEach(() => {
    mockProofJobs.mockReturnValue({ data: undefined, isLoading: false });
  });

  it("renders heading and request proof action", () => {
    renderWithProviders(<ProofsPage />);

    expect(screen.getByText("Proof Jobs")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Request Proof/i })).toBeTruthy();
  });

  it("shows loading skeleton while jobs load", () => {
    mockProofJobs.mockReturnValue({ data: undefined, isLoading: true });

    const { container } = renderWithProviders(<ProofsPage />);

    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders empty state when no jobs exist", () => {
    mockProofJobs.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    });

    renderWithProviders(<ProofsPage />);

    expect(screen.getByText("No proof jobs yet")).toBeTruthy();
    expect(screen.getByText("Request a proof to see it tracked here")).toBeTruthy();
  });

  it("renders proof jobs table with status and links", () => {
    mockProofJobs.mockReturnValue({
      data: {
        items: [
          {
            task_id: "task-abc-1234567890",
            circuit_id: 19,
            status: "proving",
            num_partitions: 8,
            partitions_completed: 2,
            redundancy: 2,
            actual_time_ms: 1200,
            requester_hotkey: "5D4vRequesterHotkey",
          },
        ],
      },
      isLoading: false,
    });

    renderWithProviders(<ProofsPage />);

    expect(screen.getByText("Task ID")).toBeTruthy();
    expect(screen.getByRole("link", { name: /task-abc-123/i })).toHaveAttribute(
      "href",
      "/proofs/task-abc-1234567890",
    );
    expect(screen.getAllByText("proving").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("2/8")).toBeInTheDocument();
    expect(screen.getByText("2x")).toBeInTheDocument();
    expect(screen.getByText("1.2s")).toBeInTheDocument();
  });
});
