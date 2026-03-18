import { Skeleton } from "@/components/ui/skeleton";

export default function CircuitsLoading() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Skeleton className="h-10 w-48" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-40 rounded-xl" />
        ))}
      </div>
    </div>
  );
}
