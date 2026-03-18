import { Skeleton } from "@/components/ui/skeleton";

export default function ProofsLoading() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-12 w-full rounded-lg" />
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-14 rounded-lg" />
        ))}
      </div>
    </div>
  );
}
