"use client";

import { useEffect, useRef } from "react";
import { SEVERITY_LABEL } from "@/lib/severity";
import { whereOf } from "@/lib/layout";
import type { Warning } from "@/lib/types";
import { SeverityBadge } from "./SeverityBadge";
import { SlideToResolve } from "./SlideToResolve";

type Props = {
  warning: Warning;
  selected: boolean;
  /** Já assumiste este aviso ("A tratar"). */
  claimed: boolean;
  onSelect: () => void;
  /** "Vou eu" (assumir) e "Já não vou" (desistir). */
  onClaim: () => void;
  /** Deslizou até ao fim: o aviso está resolvido. Recebe a linha, para a animação de saída. */
  onResolve: (row: HTMLElement | null) => void;
};

export function WarningRow({ warning, selected, claimed, onSelect, onClaim, onResolve }: Props) {
  const { event, name, face, severity, task } = warning;
  const root = useRef<HTMLDivElement>(null);

  // Ao assumir, a linha cresce (aparece o cursor de resolver): rola até ficar tudo à vista.
  useEffect(() => {
    if (!claimed) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    root.current?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  }, [claimed]);

  return (
    <div ref={root}>
      <div className="mx-2 h-px bg-divider" />
      <div className={`rounded-badge px-2 py-2.5 ${selected ? "bg-ink/8" : ""}`}>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onSelect}
            className="m-0 flex min-h-row min-w-0 flex-1 cursor-pointer items-center gap-3 border-0 bg-transparent p-0 text-left font-[inherit] text-inherit"
          >
            <SeverityBadge severity={severity} />
            <span className="flex min-w-0 flex-col gap-0.5">
              {claimed ? (
                <span className="mb-0.5 self-start rounded-full border-2 border-ink px-2 font-sans text-mono-id leading-snug font-extrabold">
                  A tratar
                </span>
              ) : null}
              <span className="text-product font-extrabold">{name}</span>
              <span className="font-mono text-mono-id font-semibold text-ink-secondary">{whereOf(face)}</span>
              <span className="text-message font-semibold">
                <span className="sr-only">{SEVERITY_LABEL[severity].label}: </span>
                {task}
              </span>
              <span className="text-secondary font-semibold text-ink-secondary">há {event.minutes_ago} min</span>
            </span>
          </button>
          {claimed ? null : (
            <button
              type="button"
              onClick={onClaim}
              aria-label={`Vou eu: ${name}`}
              className="m-0 h-touch min-w-[84px] flex-none cursor-pointer rounded-full border-2 border-ink bg-ink px-3.5 text-button font-extrabold text-ink-on"
            >
              Vou eu
            </button>
          )}
        </div>
        {claimed ? (
          <div className="mt-2 flex flex-col">
            <SlideToResolve ariaLabel={`Dar como resolvido: ${name}`} onResolve={() => onResolve(root.current)} />
            <button
              type="button"
              onClick={onClaim}
              className="m-0 h-touch cursor-pointer self-end border-0 bg-transparent px-2 text-secondary font-bold text-ink-secondary underline"
            >
              Já não vou
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
