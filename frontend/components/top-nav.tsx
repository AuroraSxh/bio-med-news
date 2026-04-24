"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavLink = { href: string; label: string };

const LINKS: NavLink[] = [
  { href: "/", label: "今日" },
  { href: "/products", label: "产品动态" },
  { href: "/corporate-dynamics", label: "企业动态" },
];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1.5">
      {LINKS.map((link) => {
        const active = isActive(pathname, link.href);
        const base =
          "rounded-full px-4 py-1.5 text-[13px] transition";
        const cls = active
          ? `${base} border border-white bg-white/10 text-white`
          : `${base} border border-white/15 text-white/75 hover:border-white/40 hover:text-white`;
        return (
          <Link key={link.href} href={link.href} className={cls}>
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
