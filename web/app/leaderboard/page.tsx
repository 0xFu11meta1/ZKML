"use client";

import { useState, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useProvers, useNetworkStats } from "@/lib/api";
import { formatBytes, formatNumber } from "@/lib/utils";
import { Trophy, Medal, Award, TrendingUp } from "lucide-react";
import Link from "next/link";

type TimeRange = "24h" | "7d" | "30d" | "all";
type SortField = "benchmark_score" | "successful_proofs" | "uptime_ratio";

export default function LeaderboardPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [sortBy, setSortBy] = useState<SortField>("benchmark_score");
  const { data: stats, isLoading: loadingStats } = useNetworkStats();
  const { data: provers, isLoading: loadingProvers } = useProvers({ page: 1 });

  const rankedProvers = useMemo(() => {
    if (!provers?.items) return [];
    return [...provers.items]
      .filter((p) => p.online || p.total_proofs > 0)
      .sort((a, b) => {
        if (sortBy === "benchmark_score")
          return b.benchmark_score - a.benchmark_score;
        if (sortBy === "successful_proofs")
          return b.successful_proofs - a.successful_proofs;
        return b.uptime_ratio - a.uptime_ratio;
      });
  }, [provers, sortBy]);

  const rankIcon = (index: number) => {
    if (index === 0) return <Trophy className="h-5 w-5 text-yellow-500" />;
    if (index === 1) return <Medal className="h-5 w-5 text-gray-400" />;
    if (index === 2) return <Award className="h-5 w-5 text-orange-400" />;
    return (
      <span className="flex h-5 w-5 items-center justify-center text-xs text-gray-400">
        {index + 1}
      </span>
    );
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Leaderboard</h1>
        <p className="mt-1 text-gray-500">
          Top prover nodes ranked by performance
        </p>
      </div>

      {/* Summary Stats */}
      {loadingStats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : stats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Active Provers"
            value={`${stats.online_provers}`}
            icon={<TrendingUp className="h-5 w-5 text-brand-600" />}
          />
          <StatCard
            title="Total Proofs"
            value={formatNumber(stats.total_proofs_generated)}
            icon={<Trophy className="h-5 w-5 text-yellow-500" />}
          />
          <StatCard
            title="Total GPU VRAM"
            value={formatBytes(stats.total_gpu_vram_bytes)}
            icon={<Medal className="h-5 w-5 text-purple-600" />}
          />
          <StatCard
            title="Avg Proof Time"
            value={`${(stats.avg_proof_time_ms / 1000).toFixed(1)}s`}
            icon={<Award className="h-5 w-5 text-green-600" />}
          />
        </div>
      ) : null}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
          {(["24h", "7d", "30d", "all"] as TimeRange[]).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                timeRange === range
                  ? "bg-white text-brand-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-900"
              }`}
            >
              {range === "all" ? "All Time" : range.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
          {(
            [
              { key: "benchmark_score", label: "Benchmark" },
              { key: "successful_proofs", label: "Proofs" },
              { key: "uptime_ratio", label: "Uptime" },
            ] as { key: SortField; label: string }[]
          ).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setSortBy(key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                sortBy === key
                  ? "bg-white text-brand-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-900"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Leaderboard Table */}
      {loadingProvers ? (
        <Skeleton className="h-96 rounded-xl" />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="px-4 py-3 font-medium w-12">Rank</th>
                    <th className="px-4 py-3 font-medium">Prover</th>
                    <th className="px-4 py-3 font-medium">GPU</th>
                    <th className="px-4 py-3 font-medium text-right">
                      Benchmark
                    </th>
                    <th className="px-4 py-3 font-medium text-right">
                      Proofs Completed
                    </th>
                    <th className="px-4 py-3 font-medium text-right">
                      Success Rate
                    </th>
                    <th className="px-4 py-3 font-medium text-right">Uptime</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rankedProvers.map((p, index) => {
                    const successRate =
                      p.total_proofs > 0
                        ? (p.successful_proofs / p.total_proofs) * 100
                        : 0;
                    return (
                      <tr
                        key={p.hotkey}
                        className={`border-b last:border-0 hover:bg-gray-50 ${
                          index < 3 ? "bg-gray-50/50" : ""
                        }`}
                      >
                        <td className="px-4 py-3">{rankIcon(index)}</td>
                        <td className="px-4 py-3">
                          <Link
                            href={`/provers/${p.hotkey}`}
                            className="font-mono text-xs text-brand-600 hover:underline"
                          >
                            {p.hotkey.slice(0, 10)}...
                          </Link>
                          <p className="text-xs text-gray-400">
                            {p.gpu_name || "Unknown GPU"}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="secondary">{p.gpu_backend}</Badge>
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-semibold">
                          {p.benchmark_score.toFixed(1)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {formatNumber(p.successful_proofs)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span
                            className={
                              successRate >= 95
                                ? "text-green-600"
                                : successRate >= 80
                                  ? "text-yellow-600"
                                  : "text-red-500"
                            }
                          >
                            {successRate.toFixed(1)}%
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {(p.uptime_ratio * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={p.online ? "success" : "destructive"}>
                            {p.online ? "Online" : "Offline"}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                  {rankedProvers.length === 0 && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-12 text-center text-gray-400"
                      >
                        No provers found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
          {icon}
        </div>
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
