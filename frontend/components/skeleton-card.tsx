export function SkeletonCard() {
  return (
    <div className="flex flex-col rounded-lg bg-white dark:bg-apple-darkSurface3">
      <div className="h-40 w-full animate-pulse rounded-t-lg bg-[#ededf2] dark:bg-apple-darkSurface1" />
      <div className="p-4">
        <div className="flex justify-between">
          <div className="h-5 w-24 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
          <div className="h-4 w-20 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
        </div>
        <div className="mt-4 h-5 w-full animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
        <div className="mt-2 h-5 w-4/5 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
        <div className="mt-4 h-3 w-28 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
        <div className="mt-4 space-y-2">
          <div className="h-4 w-full animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
          <div className="h-4 w-11/12 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-[#ededf2] dark:bg-apple-darkSurface1" />
        </div>
      </div>
    </div>
  );
}
