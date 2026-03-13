"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/lib/api";
import { Key, Plus, Trash2, Copy, Shield } from "lucide-react";
import { timeAgo } from "@/lib/utils";

export default function SettingsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const { data: apiKeys, isLoading } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();

  const [newKeyLabel, setNewKeyLabel] = useState("");
  const [newKeyLimit, setNewKeyLimit] = useState(1000);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  if (status === "loading") return null;
  if (status === "unauthenticated") {
    router.push("/auth/signin");
    return null;
  }

  const handleCreate = async () => {
    const result = await createKey.mutateAsync({
      label: newKeyLabel,
      daily_limit: newKeyLimit,
    });
    setCreatedKey(result.key);
    setShowForm(false);
    setNewKeyLabel("");
    setNewKeyLimit(1000);
  };

  const handleRevoke = async (id: number) => {
    if (!confirm("Revoke this API key? This cannot be undone.")) return;
    await revokeKey.mutateAsync(id);
  };

  const copyKey = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" /> Profile
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500 w-20">Hotkey:</span>
            <code className="bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-xs">
              {session?.user?.name ?? "—"}
            </code>
          </div>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" /> API Keys
            </CardTitle>
            <Button
              size="sm"
              onClick={() => setShowForm(!showForm)}
              variant={showForm ? "outline" : "default"}
            >
              <Plus className="h-4 w-4 mr-1" />
              {showForm ? "Cancel" : "Create Key"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* New key banner */}
          {createdKey && (
            <div className="rounded-lg border border-green-200 bg-green-50 dark:bg-green-900/20 p-4">
              <p className="text-sm font-medium text-green-700 dark:text-green-400 mb-1">
                API key created — copy it now, it will not be shown again.
              </p>
              <div className="flex items-center gap-2">
                <code className="bg-white dark:bg-gray-900 border px-3 py-1 rounded text-xs flex-1 overflow-auto">
                  {createdKey}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => copyKey(createdKey)}
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="mt-2 text-xs"
                onClick={() => setCreatedKey(null)}
              >
                Dismiss
              </Button>
            </div>
          )}

          {/* Create form */}
          {showForm && (
            <div className="rounded-lg border p-4 space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Label</label>
                <input
                  type="text"
                  value={newKeyLabel}
                  onChange={(e) => setNewKeyLabel(e.target.value)}
                  placeholder="e.g. CI pipeline"
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  maxLength={128}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Daily Limit
                </label>
                <input
                  type="number"
                  value={newKeyLimit}
                  onChange={(e) =>
                    setNewKeyLimit(
                      Math.max(1, Math.min(100000, Number(e.target.value))),
                    )
                  }
                  min={1}
                  max={100000}
                  className="w-32 rounded-md border px-3 py-1.5 text-sm"
                />
              </div>
              <Button
                size="sm"
                onClick={handleCreate}
                disabled={createKey.isPending}
              >
                {createKey.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
          )}

          {/* List */}
          {isLoading ? (
            <p className="text-sm text-gray-400">Loading…</p>
          ) : !apiKeys?.length ? (
            <p className="text-sm text-gray-400">
              No API keys yet. Create one to get started.
            </p>
          ) : (
            <div className="divide-y rounded-lg border">
              {apiKeys.map((k: Record<string, unknown>) => (
                <div
                  key={k.id as number}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {(k.label as string) || "Unnamed key"}
                      </span>
                      <Badge variant="secondary" className="text-xs">
                        {String(k.requests_today ?? 0)} /{" "}
                        {String(k.daily_limit ?? 1000)}
                      </Badge>
                      {k.expires_at && (
                        <Badge variant="outline" className="text-xs">
                          Expires {timeAgo(k.expires_at as string)}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      Created {timeAgo(k.created_at as string)}
                      {k.last_used_at
                        ? ` · Last used ${timeAgo(k.last_used_at as string)}`
                        : " · Never used"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-500 hover:text-red-700"
                    onClick={() => handleRevoke(k.id as number)}
                    disabled={revokeKey.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
