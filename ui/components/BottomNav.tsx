"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Mapa" },
  { href: "/lista", label: "Lista" },
  { href: "/tarefa", label: "Tarefa" },
];

/**
 * Navegação entre as três vistas da mesma aplicação (o estado é partilhado, por isso nada se perde).
 * Esconde-se (desce) quando uma tarefa do mapa ocupa o sítio dela.
 */
export function BottomNav({ hidden }: { hidden: boolean }) {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Vistas"
      inert={hidden}
      className={`absolute inset-x-0 bottom-0 z-20 flex h-12 items-center gap-1 bg-ground px-gutter pb-[env(safe-area-inset-bottom)] motion-safe:transition-transform motion-safe:duration-[380ms] motion-safe:ease-[cubic-bezier(.4,0,.2,1)] ${
        hidden ? "translate-y-full" : "translate-y-0"
      }`}
    >
      {TABS.map((tab) => {
        const active = tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={`flex h-touch flex-1 items-center justify-center rounded-segmented-item text-button font-extrabold no-underline ${
              active ? "bg-ink text-ink-on" : "text-ink"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
