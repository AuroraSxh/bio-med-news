import { SkeletonCard } from "@/components/skeleton-card";

export default function Loading() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="h-24 rounded-lg border border-slate-200 bg-white" />
        <div className="h-44 rounded-lg border border-slate-200 bg-white" />
        <div className="columns-1 gap-4 md:columns-2 xl:columns-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      </div>
    </main>
  );
}
