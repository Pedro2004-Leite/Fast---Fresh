"use client";

import { useRef, useState, type PointerEvent } from "react";

const KNOB = 44;
const PAD = 2;
/** A partir de que fração do percurso o gesto conta como "resolvido". */
const DONE_AT = 0.9;

type Props = {
  ariaLabel: string;
  onResolve: () => void;
  /** O texto do trilho (mais curto onde há pouca largura). */
  label?: string;
};

/**
 * "Deslize para dar como resolvido": o cursor arrasta-se e o trilho enche a verde atrás dele.
 * Só resolve ao chegar ao fim; se largares antes, volta ao início. Um toque simples não faz nada.
 * Para teclado e leitores de ecrã, o cursor é um botão: Enter/Espaço (ou o toque do leitor) resolve.
 */
export function SlideToResolve({ ariaLabel, onResolve, label = "Deslize para dar como resolvido" }: Props) {
  const track = useRef<HTMLDivElement>(null);
  const drag = useRef<{ startX: number; startProgress: number; last: number } | null>(null);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [done, setDone] = useState(false);

  const range = () => Math.max(1, (track.current?.clientWidth ?? 0) - KNOB - PAD * 2);
  const clamp = (v: number) => Math.min(1, Math.max(0, v));

  const finish = () => {
    setProgress(1);
    setDone(true);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.setTimeout(onResolve, reduced ? 0 : 140);
  };

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    if (done) return;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // o ponteiro já não está ativo: o arrasto continua sem captura
    }
    drag.current = { startX: e.clientX, startProgress: progress, last: progress };
    setDragging(true);
  };

  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    d.last = clamp(d.startProgress + (e.clientX - d.startX) / range());
    setProgress(d.last);
  };

  const release = () => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setDragging(false);
    if (d.last >= DONE_AT) finish(); // `last` e não o estado: num arrasto rápido o estado pode estar um passo atrás
    else setProgress(0);
  };

  // posições em CSS (percentagem do trilho): não é preciso medir durante a renderização
  const knobLeft = `calc(${PAD}px + ${progress} * (100% - ${KNOB + PAD * 2}px))`;
  const fillWidth = `calc(${PAD}px + ${progress} * (100% - ${KNOB + PAD * 2}px) + ${KNOB / 2}px)`;
  const ease = dragging ? "" : "motion-safe:transition-[left,width] motion-safe:duration-150";

  return (
    <div
      ref={track}
      className="relative h-12 touch-none overflow-hidden rounded-full bg-chip select-none"
      role="group"
      aria-label={ariaLabel}
    >
      <div
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 bg-done ${ease}`}
        style={{ width: fillWidth }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center overflow-hidden pr-2 pl-[62px] text-secondary font-extrabold whitespace-nowrap text-ink"
      >
        {done ? "Resolvido" : label}
      </span>
      <button
        type="button"
        aria-label={`${ariaLabel}. Deslize para a direita, ou prima Enter.`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={release}
        onPointerCancel={release}
        onClick={(e) => {
          if (e.detail === 0 && !done) finish(); // teclado ou leitor de ecrã (um toque normal não resolve)
        }}
        className={`absolute top-0.5 m-0 flex size-touch cursor-grab touch-none items-center justify-center rounded-full border-0 bg-ink p-0 text-ink-on active:cursor-grabbing ${ease}`}
        style={{ left: knobLeft }}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          className="stroke-current stroke-[2.6]"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d={done ? "M20 6 9 17l-5-5" : "M5 12h14M13 6l6 6-6 6"} />
        </svg>
      </button>
    </div>
  );
}
