"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { whereOf } from "@/lib/layout";
import type { Warning } from "@/lib/types";
import { SEVERITY_BG } from "./SeverityBadge";
import { SlideToResolve } from "./SlideToResolve";

type Props = {
  open: boolean;
  onClose: () => void;
  /** A altura do conteúdo (muda quando se assume o aviso): o mapa encolhe para o que sobra. */
  onHeight: (height: number) => void;
  /** O que mostra: uma tarefa (com "Vou eu") ou só informação de um retângulo (modo Nível). */
  content:
    | { kind: "warning"; warning: Warning; claimed: boolean; onClaim: () => void; onResolve: (row: HTMLElement | null) => void }
    | { kind: "info"; title: string; where: string; lines: string[] }
    | null;
};

function Close({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Fechar"
      className="absolute top-1 right-1.5 m-0 size-touch cursor-pointer border-0 bg-transparent p-0 text-[22px] font-extrabold text-ink-secondary"
    >
      ×
    </button>
  );
}

/**
 * A tarefa do aviso tocado, em baixo, no sítio onde estava a barra de separadores.
 * Desliza para cima ao abrir e para baixo ao fechar; o mapa encolhe para o que sobra.
 */
export function MapTaskCard({ open, onClose, onHeight, content }: Props) {
  const inner = useRef<HTMLDivElement>(null);
  const height = useRef(0);

  useEffect(() => {
    const el = inner.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const h = Math.ceil(el.getBoundingClientRect().height);
      if (h > 0 && h !== height.current) {
        height.current = h;
        onHeight(h);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [onHeight]);

  let body: ReactNode = null;
  let key = "vazio";
  if (content?.kind === "warning") {
    const { warning, claimed, onClaim, onResolve } = content;
    key = warning.area_id;
    body = <WarningBody warning={warning} claimed={claimed} onClaim={onClaim} onResolve={onResolve} onClose={onClose} />;
  } else if (content?.kind === "info") {
    key = `info-${content.title}`;
    body = (
      <div className="relative px-gutter pt-3 pb-4">
        <Close onClose={onClose} />
        <div className="flex min-h-14 flex-col justify-center gap-0.5 pr-10">
          <b className="text-product-card font-extrabold">{content.title}</b>
          <span className="font-mono text-mono-id font-semibold text-ink-secondary">{content.where}</span>
          {content.lines.map((line) => (
            <span key={line} className="text-message font-semibold">
              {line}
            </span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      aria-hidden={!open}
      inert={!open}
      className={`absolute inset-x-0 bottom-0 z-30 rounded-t-sheet bg-sheet shadow-sheet motion-safe:transition-transform motion-safe:duration-[380ms] motion-safe:ease-[cubic-bezier(.4,0,.2,1)] ${
        open ? "translate-y-0" : "translate-y-[110%]"
      }`}
    >
      <div ref={inner} key="medida">
        <div key={key}>{body}</div>
      </div>
    </div>
  );
}

function WarningBody({
  warning,
  claimed,
  onClaim,
  onResolve,
  onClose,
}: {
  warning: Warning;
  claimed: boolean;
  onClaim: () => void;
  onResolve: (row: HTMLElement | null) => void;
  onClose: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const { event, name, face, severity, task } = warning;
  return (
    <div ref={root} className="relative px-gutter pt-3 pb-4">
      <Close onClose={onClose} />
      <div className="flex min-h-14 items-center gap-3 pr-10">
        <span className="flex size-touch flex-none items-center justify-center" aria-hidden="true">
          <span data-severity-dot className={`size-7 rounded-full ${SEVERITY_BG[severity]}`} />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          {claimed ? (
            <span className="self-start rounded-full border-2 border-ink px-2 font-sans text-mono-id leading-snug font-extrabold">
              A tratar · tu
            </span>
          ) : null}
          <b className="text-product-card font-extrabold">{name}</b>
          <span className="font-mono text-mono-id font-semibold text-ink-secondary">{whereOf(face)}</span>
          <span className="text-message font-semibold">{task}</span>
          <span className="text-secondary font-semibold text-ink-secondary">há {event.minutes_ago} min</span>
        </div>
      </div>
      {claimed ? (
        <div className="mt-2.5 flex flex-col">
          <SlideToResolve ariaLabel={`Dar como resolvido: ${name}`} onResolve={() => onResolve(root.current)} />
          <button
            type="button"
            onClick={onClaim}
            className="m-0 h-touch cursor-pointer self-end border-0 bg-transparent px-2 text-secondary font-bold text-ink-secondary underline"
          >
            Já não vou
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onClaim}
          aria-label={`Vou eu: ${name}`}
          className="m-0 mt-2.5 h-button w-full cursor-pointer rounded-full border-2 border-ink bg-ink px-4 text-button font-extrabold text-ink-on"
        >
          Vou eu
        </button>
      )}
    </div>
  );
}
