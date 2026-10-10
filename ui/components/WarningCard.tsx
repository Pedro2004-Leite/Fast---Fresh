"use client";

import { useRef } from "react";
import { whereOf } from "@/lib/layout";
import type { Warning } from "@/lib/types";
import { MiniBench } from "./MiniBench";
import { SeverityPill } from "./SeverityPill";
import { SlideToResolve } from "./SlideToResolve";
import { SEVERITY_LABEL } from "@/lib/severity";

type Props = {
  warning: Warning;
  /** Já assumiste este aviso ("A tratar"). */
  claimed: boolean;
  onClaim: () => void;
  onResolve: (row: HTMLElement | null) => void;
  /** Tocar no aviso: abre o Mapa com ele selecionado. */
  onShowOnMap: () => void;
};

/** Um aviso em cartão: mini-mapa, gravidade, nome, tarefa, distância e "Vou eu" (depois, deslizar para resolver). */
export function WarningCard({ warning, claimed, onClaim, onResolve, onShowOnMap }: Props) {
  const { event, name, face, severity, task, distanceM } = warning;
  const root = useRef<HTMLElement>(null);
  const where = whereOf(face);

  return (
    <article ref={root} className="flex flex-none flex-col gap-3 rounded-card bg-sheet p-3">
      <button
        type="button"
        onClick={onShowOnMap}
        aria-label={`Ver no mapa: ${name}`}
        className="m-0 flex w-full cursor-pointer gap-3 border-0 bg-transparent p-0 text-left font-[inherit] text-inherit active:opacity-70"
      >
        <MiniBench
          warning={warning}
          label={`${name}, ${where.toLowerCase()}, ${SEVERITY_LABEL[severity].label.toLowerCase()}, a ${distanceM} metros de ti`}
        />
        <div className="flex min-w-0 flex-1 flex-col gap-[5px]">
          <div className="flex items-center justify-between gap-2">
            <SeverityPill severity={severity} />
            <span className="text-secondary font-semibold text-ink-secondary">há {event.minutes_ago} min</span>
          </div>
          {claimed ? (
            <span className="self-start rounded-full border-2 border-ink px-2 font-sans text-mono-id leading-snug font-extrabold">
              A tratar · tu
            </span>
          ) : null}
          <span className="text-product-card leading-[1.15] font-extrabold">{name}</span>
          <div className="text-message font-semibold">{task}</div>
          {event.complaint ? (
            <div className="text-secondary leading-[1.25] italic">Reclamação: “{event.complaint}”</div>
          ) : null}
          <div className="font-mono text-mono-id leading-[1.3] font-semibold text-ink-secondary">
            {where} · a {distanceM} m
          </div>
        </div>
      </button>
      {claimed ? (
        <div className="flex flex-col">
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
          className="m-0 h-button w-full cursor-pointer rounded-full border-2 border-ink bg-ink px-4 text-button font-extrabold text-ink-on"
        >
          Vou eu
        </button>
      )}
    </article>
  );
}
