import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "outline" | "dark" | "ghost";

const base =
  "inline-flex items-center justify-center text-sm font-normal transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  default:
    "rounded-lg border border-transparent bg-apple-blue px-[15px] py-2 text-white hover:bg-[#0077ed]",
  outline:
    "rounded-pill border border-apple-blue bg-transparent px-[18px] py-2 text-apple-blue hover:bg-apple-blue/5 dark:text-apple-linkDark dark:border-apple-linkDark dark:hover:bg-apple-linkDark/10",
  dark:
    "rounded-lg border border-transparent bg-apple-text px-[15px] py-2 text-white hover:bg-black",
  ghost:
    "rounded-lg border border-transparent bg-transparent px-[15px] py-2 text-apple-text hover:bg-black/5 dark:text-white dark:hover:bg-white/10",
};

export function Button({
  className,
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={cn(base, variants[variant], className)}
      {...props}
    />
  );
}
