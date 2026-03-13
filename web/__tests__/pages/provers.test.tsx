import { screen } from "@testing-library/react";
import { renderWithProviders } from "../helpers";

const mockStats = jest.fn();
const mockProvers = jest.fn();

jest.mock("@/lib/api", () => ({
  useNetworkStats: () => ({ data: mockStats(), isLoading: false }),
  useProvers: () => ({ data: mockProvers(), isLoading: false }),
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

import ProversPage from "@/app/provers/page";

describe("ProversPage", () => {
  beforeEach(() => {
    mockStats.mockReturnValue(undefined);
    mockProvers.mockReturnValue(undefined);
  });

  it("renders heading and subtext", () => {
    renderWithProviders(<ProversPage />);
    expect(screen.getByText("Prover Network")).toBeInTheDocument();
    expect(
      screen.getByText("GPU-accelerated nodes generating ZK proofs"),
    ).toBeInTheDocument();
  });

  it("displays stat cards when network stats available", () => {
    mockStats.mockReturnValue({
      online_provers: 3,
      total_provers: 8,
      total_proofs_generated: 2500,
      total_gpu_vram_bytes: 8589934592, // 8 GB
      avg_proof_time_ms: 1200,
      active_jobs: 1,
      total_circuits: 5,
    });

    renderWithProviders(<ProversPage />);
    expect(screen.getByText("3/8")).toBeInTheDocument();
    expect(screen.getByText("2.5K")).toBeInTheDocument();
    expect(screen.getByText("8.0 GB")).toBeInTheDocument();
    expect(screen.getByText("1.2s")).toBeInTheDocument();
  });

  it("shows prover table headers", () => {
    mockProvers.mockReturnValue({ items: [], total: 0 });

    renderWithProviders(<ProversPage />);
    expect(screen.getByText("Hotkey")).toBeInTheDocument();
    expect(screen.getByText("GPU")).toBeInTheDocument();
    expect(screen.getByText("Backend")).toBeInTheDocument();
    expect(screen.getByText("VRAM")).toBeInTheDocument();
    expect(screen.getByText("Benchmark")).toBeInTheDocument();
  });

  it("renders prover rows with correct data", () => {
    mockProvers.mockReturnValue({
      items: [
        {
          hotkey: "5FLSigC9HGRKVhB9FiEo4Y3koPsNmBmLJbpXg2mp1hXcS59Y",
          gpu_name: "RTX 4090",
          gpu_backend: "cuda",
          vram_bytes: 25769803776, // 24 GB
          benchmark_score: 95.2,
          successful_proofs: 100,
          failed_proofs: 3,
          uptime_ratio: 0.995,
          is_online: true,
        },
      ],
      total: 1,
    });

    renderWithProviders(<ProversPage />);
    expect(screen.getByText("RTX 4090")).toBeInTheDocument();
    expect(screen.getByText("cuda")).toBeInTheDocument();
    expect(screen.getByText("24.0 GB")).toBeInTheDocument();
    expect(screen.getByText("95.2")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
