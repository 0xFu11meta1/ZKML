"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { useSearchCircuits, useProvers } from "@/lib/api";
import { Search as SearchIcon, Cpu, Network } from "lucide-react";
import { formatNumber } from "@/lib/utils";

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialQuery = searchParams.get("q") || "";
  const initialPage = Number(searchParams.get("page")) || 1;

  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [page, setPage] = useState(initialPage);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Update URL
  useEffect(() => {
    if (debouncedQuery) {
      router.replace(
        `/search?q=${encodeURIComponent(debouncedQuery)}&page=${page}`,
      );
    }
  }, [debouncedQuery, page, router]);

  const { data: circuits, isLoading: circuitsLoading } = useSearchCircuits(
    debouncedQuery,
    page,
  );
  const { data: provers } = useProvers({
    page: 1,
  });

  // Filter provers client-side by query (hotkey or gpu_name)
  const matchedProvers =
    debouncedQuery && provers?.items
      ? provers.items.filter(
          (p) =>
            p.hotkey.toLowerCase().includes(debouncedQuery.toLowerCase()) ||
            p.gpu_name.toLowerCase().includes(debouncedQuery.toLowerCase()),
        )
      : [];

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Search</h1>
        <p className="mt-1 text-gray-500">
          Search across circuits, proofs, and provers.
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <SearchIcon className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search circuits, provers, proof systems..."
          autoFocus
          className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-12 pr-4 text-base shadow-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 transition-colors"
        />
      </div>

      {/* Results */}
      {debouncedQuery && (
        <div className="space-y-8">
          {/* Circuits */}
          <section>
            <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
              <Cpu className="h-5 w-5 text-purple-600" />
              Circuits
              {circuits && <Badge variant="secondary">{circuits.total}</Badge>}
            </h2>

            {circuitsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-16 animate-pulse rounded-lg bg-gray-100"
                  />
                ))}
              </div>
            ) : circuits?.items && circuits.items.length > 0 ? (
              <>
                <div className="space-y-2">
                  {circuits.items.map((circuit) => (
                    <Link key={circuit.id} href={`/circuits/${circuit.id}`}>
                      <Card className="cursor-pointer transition-shadow hover:shadow-md">
                        <CardContent className="flex items-center justify-between p-4">
                          <div>
                            <p className="font-semibold">{circuit.name}</p>
                            <p className="text-sm text-gray-500">
                              {circuit.proof_type} · {circuit.circuit_type} ·{" "}
                              {formatNumber(circuit.num_constraints)}{" "}
                              constraints
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge>{circuit.proof_type}</Badge>
                            <span className="text-sm text-gray-400">
                              v{circuit.version}
                            </span>
                          </div>
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
                {circuits.total > 20 && (
                  <div className="mt-4">
                    <Pagination
                      page={page}
                      totalPages={Math.ceil(circuits.total / 20)}
                      onPageChange={handlePageChange}
                    />
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-gray-400">
                No circuits match &ldquo;{debouncedQuery}&rdquo;
              </p>
            )}
          </section>

          {/* Provers */}
          {matchedProvers.length > 0 && (
            <section>
              <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
                <Network className="h-5 w-5 text-brand-600" />
                Provers
                <Badge variant="secondary">{matchedProvers.length}</Badge>
              </h2>
              <div className="space-y-2">
                {matchedProvers.slice(0, 10).map((prover) => (
                  <Link key={prover.hotkey} href={`/provers/${prover.hotkey}`}>
                    <Card className="cursor-pointer transition-shadow hover:shadow-md">
                      <CardContent className="flex items-center justify-between p-4">
                        <div>
                          <p className="font-mono text-sm font-semibold">
                            {prover.hotkey.slice(0, 20)}...
                          </p>
                          <p className="text-sm text-gray-500">
                            {prover.gpu_name} · {prover.gpu_backend}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={prover.online ? "success" : "secondary"}
                          >
                            {prover.online ? "Online" : "Offline"}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Empty state */}
      {!debouncedQuery && (
        <div className="py-16 text-center">
          <SearchIcon className="mx-auto h-12 w-12 text-gray-300" />
          <p className="mt-4 text-gray-500">
            Type a search query to find circuits, provers, and more.
          </p>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="py-16 text-center text-gray-400">Loading...</div>
      }
    >
      <SearchContent />
    </Suspense>
  );
}
