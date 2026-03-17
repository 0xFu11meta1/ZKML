"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useHealth,
  useNetworkStats,
  useProofJobs,
  useProvers,
} from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Server,
  Cpu,
  Zap,
  Users,
  XCircle,
} from "lucide-react";

export default function AdminPage() {
  const { data: health, isLoading: loadingHealth } = useHealth();
  const { data: stats, isLoading: loadingStats } = useNetworkStats();
  const { data: activeJobs, isLoading: loadingJobs } = useProofJobs({
    status: "dispatched",
    page: 1,
  });
  const { data: queuedJobs } = useProofJobs({ status: "queued", page: 1 });
  const { data: provers, isLoading: loadingProvers } = useProvers({
    page: 1,
  });

  const onlineProvers =
    provers?.items.filter((p) => p.online).length ?? 0;
  const offlineProvers =
    (provers?.items.length ?? 0) - onlineProvers;

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin Dashboard</h1>
        <p className="mt-1 text-gray-500">
          System health, active jobs, and prover management
        </p>
      </div>

      {/* System Health */}
      <section>
        <h2 className="mb-4 text-xl font-semibold flex items-center gap-2">
          <Activity className="h-5 w-5" />
          System Health
        </h2>
        {loadingHealth || loadingStats ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <HealthCard
              title="Registry API"
              status={health?.status === "ok" ? "healthy" : "degraded"}
              detail={health?.network || "unknown"}
            />
            <HealthCard
              title="Online Provers"
              status={onlineProvers > 0 ? "healthy" : "degraded"}
              detail={`${onlineProvers} online / ${offlineProvers} offline`}
            />
            <HealthCard
              title="Active Jobs"
              status="healthy"
              detail={`${activeJobs?.total ?? 0} dispatched, ${queuedJobs?.total ?? 0} queued`}
            />
            <HealthCard
              title="Network Proofs"
              status="healthy"
              detail={formatNumber(stats?.total_proofs_generated ?? 0)}
            />
          </div>
        )}
      </section>

      {/* Active Jobs */}
      <section>
        <h2 className="mb-4 text-xl font-semibold flex items-center gap-2">
          <Zap className="h-5 w-5" />
          Active Proof Jobs
        </h2>
        {loadingJobs ? (
          <Skeleton className="h-48 rounded-xl" />
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="px-4 py-3 font-medium">Job ID</th>
                      <th className="px-4 py-3 font-medium">Circuit</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Requester</th>
                      <th className="px-4 py-3 font-medium text-right">
                        Partitions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeJobs?.items.map((job) => (
                      <tr
                        key={job.id}
                        className="border-b last:border-0 hover:bg-gray-50"
                      >
                        <td className="px-4 py-3 font-mono text-xs">
                          {String(job.id).slice(0, 8)}...
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">
                          {String(job.circuit_id)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge
                            variant={
                              job.status === "completed"
                                ? "success"
                                : job.status === "failed"
                                ? "destructive"
                                : "secondary"
                            }
                          >
                            {job.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">
                          {job.requester_hotkey.slice(0, 10)}...
                        </td>
                        <td className="px-4 py-3 text-right">
                          {job.total_partitions}
                        </td>
                      </tr>
                    ))}
                    {(!activeJobs?.items || activeJobs.items.length === 0) && (
                      <tr>
                        <td
                          colSpan={5}
                          className="px-4 py-12 text-center text-gray-400"
                        >
                          No active jobs
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </section>

      {/* Prover Overview */}
      <section>
        <h2 className="mb-4 text-xl font-semibold flex items-center gap-2">
          <Users className="h-5 w-5" />
          Prover Overview
        </h2>
        {loadingProvers ? (
          <Skeleton className="h-48 rounded-xl" />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Online Provers</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {provers?.items
                    .filter((p) => p.online)
                    .slice(0, 10)
                    .map((p) => (
                      <div
                        key={p.hotkey}
                        className="flex items-center justify-between rounded-lg border p-3"
                      >
                        <div>
                          <span className="font-mono text-xs">
                            {p.hotkey.slice(0, 12)}...
                          </span>
                          <p className="text-xs text-gray-400">
                            {p.gpu_name || "Unknown GPU"} · {p.gpu_backend}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-mono">
                            {p.benchmark_score.toFixed(1)}
                          </p>
                          <p className="text-xs text-gray-400">
                            Load: {(p.current_load ?? 0).toFixed(0)}%
                          </p>
                        </div>
                      </div>
                    ))}
                  {onlineProvers === 0 && (
                    <p className="py-4 text-center text-gray-400 text-sm">
                      No provers online
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Offline Provers</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {provers?.items
                    .filter((p) => !p.online)
                    .slice(0, 10)
                    .map((p) => (
                      <div
                        key={p.hotkey}
                        className="flex items-center justify-between rounded-lg border p-3 opacity-60"
                      >
                        <div>
                          <span className="font-mono text-xs">
                            {p.hotkey.slice(0, 12)}...
                          </span>
                          <p className="text-xs text-gray-400">
                            {p.gpu_name || "Unknown GPU"}
                          </p>
                        </div>
                        <Badge variant="destructive">Offline</Badge>
                      </div>
                    ))}
                  {offlineProvers === 0 && (
                    <p className="py-4 text-center text-gray-400 text-sm">
                      All provers online
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </section>
    </div>
  );
}

function HealthCard({
  title,
  status,
  detail,
}: {
  title: string;
  status: "healthy" | "degraded" | "down";
  detail: string;
}) {
  const icon =
    status === "healthy" ? (
      <CheckCircle2 className="h-5 w-5 text-green-600" />
    ) : status === "degraded" ? (
      <AlertTriangle className="h-5 w-5 text-yellow-600" />
    ) : (
      <XCircle className="h-5 w-5 text-red-600" />
    );

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
          {icon}
        </div>
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-sm font-medium">{detail}</p>
        </div>
      </CardContent>
    </Card>
  );
}
