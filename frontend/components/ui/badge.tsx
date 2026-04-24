import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type BadgeVariant = "default" | "secondary" | "outline" | "destructive";

const variants: Record<BadgeVariant, string> = {
  default: "border-transparent bg-apple-blue text-white",
  secondary:
    "border-transparent bg-[#ededf2] text-apple-text dark:bg-apple-darkSurface1 dark:text-white",
  outline:
    "border-apple-blue bg-transparent text-apple-blue",
  destructive: "border-transparent bg-[#ff3b30] text-white",
};

export function Badge({
  className,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
