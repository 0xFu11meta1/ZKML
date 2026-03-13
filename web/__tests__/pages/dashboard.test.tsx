import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../helpers";

// Mock the API hooks
const mockHealth = jest.fn();
const mockNetworkStats = jest.fn();
const mockProofJobs = jest.fn();
const mockProvers = jest.fn();

jest.mock("@/lib/api", () => ({
  useHealth: () => ({ data: mockHealth() }),
  useNetworkStats: () => ({ data: mockNetworkStats() }),
  useProofJobs: () => ({ data: mockProofJobs() }),
  useProvers: () => ({ data: mockProvers() }),
}));

// Mock next/link
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

import HomePage from "@/app/page";

describe("Dashboard (HomePage)", () => {
  beforeEach(() => {
    mockHealth.mockReturnValue(undefined);
    mockNetworkStats.mockReturnValue(undefined);
    mockProofJobs.mockReturnValue(undefined);
    mockProvers.mockReturnValue(undefined);
  });

  it("renders the Dashboard heading", () => {
    renderWithProviders(<HomePage />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(
      screen.getByText("GPU-Accelerated ZK Prover Network on Bittensor"),
    ).toBeInTheDocument();
  });

  it("shows dash placeholders when data is loading", () => {
    renderWithProviders(<HomePage />);
    // KPI values should show "—" when no data
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("shows network stats when data is available", () => {
    mockNetworkStats.mockReturnValue({
      online_provers: 42,
      total_provers: 100,
      total_proofs_generated: 10500,
      total_circuits: 15,
      avg_proof_time_ms: 2500,
      active_jobs: 7,
      total_gpu_vram_bytes: 85899345920, // ~80 GB
    });
    mockHealth.mockReturnValue({ status: "ok" });

    renderWithProviders(<HomePage />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("100 total")).toBeInTheDocument();
    expect(screen.getByText("10.5K")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("2.5s")).toBeInTheDocument();
    expect(screen.getByText("7 active jobs")).toBeInTheDocument();
  });

  it("shows Healthy badge when health is ok", () => {
    mockHealth.mockReturnValue({ status: "ok" });
    mockNetworkStats.mockReturnValue({
      online_provers: 1,
      total_provers: 1,
      total_proofs_generated: 0,
      total_circuits: 0,
      avg_proof_time_ms: 0,
      active_jobs: 0,
      total_gpu_vram_bytes: 0,
    });

    renderWithProviders(<HomePage />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders the Network Overview card with GPU VRAM", () => {
    mockNetworkStats.mockReturnValue({
      online_provers: 5,
      total_provers: 10,
      total_proofs_generated: 1000,
      total_circuits: 3,
      avg_proof_time_ms: 500,
      active_jobs: 2,
      total_gpu_vram_bytes: 1073741824, // 1 GB
    });

    renderWithProviders(<HomePage />);
    expect(screen.getByText("Network Overview")).toBeInTheDocument();
    expect(screen.getByText("1.0 GB")).toBeInTheDocument();
    expect(screen.getByText("5/10")).toBeInTheDocument();
  });
});
