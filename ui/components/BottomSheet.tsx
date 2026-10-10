"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

type Props = {
  /** Distância do topo do ecrã ao topo do painel quando fechado e quando aberto (px). */
  collapsedTop: number;
  expandedTop: number;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  ariaLabel: string;
  children: ReactNode;
};

/** Arrastar mais do que isto (px) decide abrir ou fechar; abaixo disto o painel volta onde estava. */
const SNAP_DISTANCE = 32;
/** Mexer menos do que isto (px) conta como toque, não como arrasto. */
const TAP_SLOP = 4;

/**
 * Painel inferior que se agarra pelo traço do topo e se arrasta para cima (abrir) ou para baixo (fechar).
 * O traço é um botão de 44 px: também abre e fecha com toque, Enter/Espaço e as setas.
 */
export function BottomSheet({ collapsedTop, expandedTop, expanded, onExpandedChange, ariaLabel, children }: Props) {
  const [dragTop, setDragTop] = useState<number | null>(null);
  const drag = useRef<{ startY: number; startTop: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);

  const restTop = expanded ? expandedTop : collapsedTop;
  const top = dragTop ?? restTop;
  const clamp = (value: number) => Math.min(collapsedTop, Math.max(expandedTop, value));

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // o ponteiro já não está ativo: o arrasto continua a funcionar sem captura
    }
    drag.current = { startY: e.clientY, startTop: restTop, moved: false };
  };

  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    const dy = e.clientY - d.startY;
    if (Math.abs(dy) > TAP_SLOP) d.moved = true;
    if (d.moved) setDragTop(clamp(d.startTop + dy));
  };

  const finish = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    drag.current = null;
    setDragTop(null);
    if (!d || !d.moved) return;
    suppressClick.current = true; // o clique que o browser dispara a seguir não é um toque
    const dy = e.clientY - d.startY;
    if (dy <= -SNAP_DISTANCE) onExpandedChange(true);
    else if (dy >= SNAP_DISTANCE) onExpandedChange(false);
  };

  const onClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    onExpandedChange(!expanded);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      onExpandedChange(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      onExpandedChange(false);
    }
  };

  return (
    <section
      aria-label={ariaLabel}
      className={`absolute inset-x-0 bottom-0 z-10 flex flex-col rounded-t-sheet bg-sheet px-gutter shadow-sheet ${
        dragTop === null ? "motion-safe:transition-[top] motion-safe:duration-200" : ""
      }`}
      style={{ top }}
    >
      <button
        type="button"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finish}
        onPointerCancel={finish}
        onClick={onClick}
        onKeyDown={onKeyDown}
        aria-expanded={expanded}
        aria-label={expanded ? "Fechar a lista de avisos" : "Abrir a lista de avisos"}
        className="-mt-3 flex h-touch w-full flex-none cursor-grab touch-none items-start justify-center border-0 bg-transparent p-0 pt-[22px] active:cursor-grabbing"
      >
        <span className="h-1 w-10 rounded-cell bg-ink opacity-25" />
      </button>
      {children}
    </section>
  );
}
