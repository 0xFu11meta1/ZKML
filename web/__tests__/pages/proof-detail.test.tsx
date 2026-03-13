import { screen } from "@testing-library/react";
import { renderWithProviders } from "../helpers";

const mockJob = jest.fn();
const mockPartitions = jest.fn();
const mockProofs = jest.fn();

jest.mock("@/lib/api", () => ({
  useProofJob: () => ({ data: mockJob(), isLoading: false }),
  useProofJobPartitions: () => ({ data: mockPartitions() }),
  useProofs: () => ({ data: mockProofs() }),
}));

jest.mock("next/navigation", () => ({
  useParams: () => ({ taskId: "task-abc-123" }),
}));

jest.mock("next/link", () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) {
    return <a href={href}>{children}</a>;
  };
});

import ProofDetailPage from "@/app/proofs/[taskId]/page";

describe("ProofDetailPage", () => {
  beforeEach(() => {
    mockJob.mockReturnValue(undefined);
    mockPartitions.mockReturnValue(undefined);
    mockProofs.mockReturnValue(undefined);
  });

  it("shows 'not found' when job is null", () => {
    renderWithProviders(<ProofDetailPage />);
    expect(screen.getByText("Proof job not found")).toBeInTheDocument();
  });

  it("renders job details when loaded", () => {
    mockJob.mockReturnValue({
      task_id: "task-abc-123",
      status: "completed",
      num_partitions: 8,
      partitions_completed: 8,
      redundancy: 2,
      actual_time_ms: 3600,
      circuit_id: 5,
      created_at: new Date().toISOString(),
      witness_cid: "bafywitness",
    });

    renderWithProviders(<ProofDetailPage />);
    expect(screen.getByText("task-abc-123")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("8 / 8")).toBeInTheDocument();
    expect(screen.getByText("2x")).toBeInTheDocument();
    expect(screen.getByText("3.6s")).toBeInTheDocument();
  });

  it("displays progress bar at 100% when all partitions done", () => {
    mockJob.mockReturnValue({
      task_id: "task-abc-123",
      status: "completed",
      num_partitions: 4,
      partitions_completed: 4,
      redundancy: 1,
      actual_time_ms: 1000,
      circuit_id: 1,
      created_at: new Date().toISOString(),
    });

    renderWithProviders(<ProofDetailPage />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("displays progress at 50% for partial completion", () => {
    mockJob.mockReturnValue({
      task_id: "task-abc-123",
      status: "proving",
      num_partitions: 10,
      partitions_completed: 5,
      redundancy: 1,
      actual_time_ms: null,
      circuit_id: 1,
      created_at: new Date().toISOString(),
    });

    renderWithProviders(<ProofDetailPage />);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("proving")).toBeInTheDocument();
  });

  it("shows back link to proof jobs list", () => {
    mockJob.mockReturnValue({
      task_id: "task-abc-123",
      status: "queued",
      num_partitions: 0,
      partitions_completed: 0,
      redundancy: 1,
      actual_time_ms: null,
      circuit_id: 1,
      created_at: new Date().toISOString(),
    });

    renderWithProviders(<ProofDetailPage />);
    const backLink = screen.getByRole("link", { name: /Back to Proof Jobs/i });
    expect(backLink).toHaveAttribute("href", "/proofs");
  });

  it("links to the circuit detail page", () => {
    mockJob.mockReturnValue({
      task_id: "task-abc-123",
      status: "proving",
      num_partitions: 4,
      partitions_completed: 2,
      redundancy: 1,
      actual_time_ms: null,
      circuit_id: 42,
      created_at: new Date().toISOString(),
    });

    renderWithProviders(<ProofDetailPage />);
    const circuitLink = screen.getByRole("link", { name: "#42" });
    expect(circuitLink).toHaveAttribute("href", "/circuits/42");
  });
});
