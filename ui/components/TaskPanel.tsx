"use client";

import { useRef } from "react";
import { whereOf } from "@/lib/layout";
import { LEVEL_TEXT } from "@/lib/levels";
import type { Warning } from "@/lib/types";
import { SEVERITY_BG } from "./SeverityBadge";
import { SeverityPill } from "./SeverityPill";
import { SlideToResolve } from "./SlideToResolve";

type Props = {
  warning: Warning;
  /** Deslizou até ao fim: está feito. Recebe o painel, para a animação de saída. */
  onResolve: (row: HTMLElement | null) => void;
  onPass: () => void;
  /** Só há uma tarefa: não há para onde passar. */
  canPass: boolean;
};

/** O título da tarefa: "Repor Banana", "Produto errado: Melancia", "Câmara 6383 sem imagem". */
export function taskTitle(w: Warning): string {
  if (w.kind === "wrong") return `${w.task}: ${w.name}`;
  if (w.kind === "blind") return w.name;
  return `${w.task} ${w.name}`;
}

/**
 * A tarefa atual, compacta (cerca de 156 px) para caber sempre: gravidade, o que fazer, onde e o nível,
 * e na mesma linha "deslizar para resolver" e "Passar". Entra deslizando quando muda a tarefa.
 */
export function TaskPanel({ warning, onResolve, onPass, canPass }: Props) {
  const { event, severity, distanceM, face, name } = warning;
  const root = useRef<HTMLDivElement>(null);
  const level = LEVEL_TEXT[event.stock_level ?? "none"];

  return (
    <div ref={root} className="flex animate-task-in flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <SeverityPill severity={severity} />
        <span className="font-mono text-secondary font-semibold text-ink-secondary">
          a {distanceM} m · há {event.minutes_ago} min
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span data-severity-dot className={`size-7 flex-none rounded-full ${SEVERITY_BG[severity]}`} aria-hidden="true" />
        <h2 className="m-0 text-title-c font-extrabold tracking-[-0.02em]">{taskTitle(warning)}</h2>
      </div>
      <div className="font-mono text-secondary font-semibold text-ink-secondary">
        {whereOf(face)} · {level}
      </div>
      {event.complaint ? (
        <div className="text-secondary leading-[1.3] italic">Reclamação: “{event.complaint}”</div>
      ) : null}
      <div className="flex items-center gap-2.5 pt-1.5">
        <div className="min-w-0 flex-1">
          <SlideToResolve
            ariaLabel={`Dar como resolvido: ${name}`}
            label="Deslize para resolver"
            onResolve={() => onResolve(root.current)}
          />
        </div>
        {canPass ? (
          <button
            type="button"
            onClick={onPass}
            className="m-0 h-12 flex-none cursor-pointer rounded-full border-2 border-ink bg-transparent px-[18px] text-button font-extrabold text-ink"
          >
            Passar
          </button>
        ) : null}
      </div>
    </div>
  );
}
