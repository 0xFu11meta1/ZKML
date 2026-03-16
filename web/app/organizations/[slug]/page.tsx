"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useOrg,
  useOrgMembers,
  useAddOrgMember,
  useRemoveOrgMember,
} from "@/lib/api";
import { Building2, Users, UserPlus, Trash2, ArrowLeft } from "lucide-react";

export default function OrgDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { data: session } = useSession();

  const { data: org, isLoading: orgLoading } = useOrg(slug);
  const { data: members, isLoading: membersLoading } = useOrgMembers(slug);
  const addMember = useAddOrgMember(slug);
  const removeMember = useRemoveOrgMember(slug);

  const [showAddForm, setShowAddForm] = useState(false);
  const [newHotkey, setNewHotkey] = useState("");
  const [newRole, setNewRole] = useState("viewer");

  const handleAddMember = () => {
    if (!newHotkey.trim()) return;
    addMember.mutate(
      { hotkey: newHotkey.trim(), role: newRole },
      {
        onSuccess: () => {
          setShowAddForm(false);
          setNewHotkey("");
          setNewRole("viewer");
        },
      },
    );
  };

  if (orgLoading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-100" />
        <div className="h-64 animate-pulse rounded-lg bg-gray-100" />
      </div>
    );
  }

  if (!org) {
    return (
      <div className="py-12 text-center">
        <p className="text-gray-500">Organization not found.</p>
        <Link href="/organizations">
          <Button variant="ghost" className="mt-4">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to organizations
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/organizations">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" /> Back
          </Button>
        </Link>
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50">
          <Building2 className="h-6 w-6 text-brand-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">{org.name}</h1>
          <p className="text-sm text-gray-400">/{org.slug}</p>
        </div>
      </div>

      {/* Members section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Members
            </CardTitle>
            <CardDescription>
              {members?.total ?? 0} member{members?.total !== 1 ? "s" : ""}
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowAddForm((v) => !v)}>
            <UserPlus className="mr-2 h-4 w-4" /> Add Member
          </Button>
        </CardHeader>
        <CardContent>
          {/* Add member form */}
          {showAddForm && (
            <div className="mb-6 rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={newHotkey}
                  onChange={(e) => setNewHotkey(e.target.value)}
                  placeholder="SS58 Hotkey (5F...)"
                  className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-brand-500"
                />
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="viewer">Viewer</option>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleAddMember}
                  disabled={addMember.isPending}
                >
                  {addMember.isPending ? "Adding..." : "Add"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowAddForm(false)}
                >
                  Cancel
                </Button>
              </div>
              {addMember.isError && (
                <p className="text-sm text-red-600">
                  {addMember.error?.message || "Failed to add member."}
                </p>
              )}
            </div>
          )}

          {/* Members table */}
          {membersLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-12 animate-pulse rounded bg-gray-100"
                />
              ))}
            </div>
          ) : members?.items && members.items.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-3 font-medium">Hotkey</th>
                  <th className="pb-3 font-medium">Role</th>
                  <th className="pb-3 font-medium">Joined</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.items.map((member) => (
                  <tr
                    key={member.hotkey}
                    className="border-b last:border-0 hover:bg-gray-50"
                  >
                    <td className="py-3 font-mono text-xs">
                      {member.hotkey.slice(0, 16)}...
                    </td>
                    <td className="py-3">
                      <Badge
                        variant={
                          member.role === "admin" ? "default" : "secondary"
                        }
                      >
                        {member.role}
                      </Badge>
                    </td>
                    <td className="py-3 text-gray-500">
                      {member.joined_at?.slice(0, 10) ?? "—"}
                    </td>
                    <td className="py-3 text-right">
                      {member.hotkey !== session?.user?.hotkey && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeMember.mutate(member.hotkey)}
                          disabled={removeMember.isPending}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="py-4 text-center text-gray-400">
              No members yet. Add a member to get started.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
