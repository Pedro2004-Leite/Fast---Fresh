"use client";

import { useCallback, useState } from "react";
import { playResolveAnimation, pulseCell } from "./resolveAnimation";
import type { Warning } from "./types";

type Hooks = {
  /** Depois de resolver (a linha já saiu). */
  onResolved?: (warning: Warning) => void;
};

/**
 * O fluxo "Vou eu" -> "Resolvido", partilhado pelos três ecrãs:
 * quais avisos estão "A tratar" e resolver com animação de saída. Resolver é definitivo.
 */
export function useResolveFlow(resolve: (areaIds: string[]) => void, hooks: Hooks = {}) {
  const [claimed, setClaimed] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState("");

  const toggleClaimed = useCallback((areaId: string) => setClaimed((cur) => ({ ...cur, [areaId]: !cur[areaId] })), []);

  /** Resolvido: a bola viaja até ao mapa (se houver) e o aviso sai. */
  const resolveWarning = async (w: Warning, row: HTMLElement | null, options: { collapse?: boolean } = {}) => {
    await playResolveAnimation(row, w.area_id, options);
    resolve(w.areaIds);
    setClaimed((cur) => {
      const next = { ...cur };
      delete next[w.area_id];
      return next;
    });
    setStatus(`${w.name} resolvido.`);
    hooks.onResolved?.(w);
    window.requestAnimationFrame(() => w.areaIds.forEach(pulseCell));
  };

  return { claimed, toggleClaimed, status, setStatus, resolveWarning };
}
