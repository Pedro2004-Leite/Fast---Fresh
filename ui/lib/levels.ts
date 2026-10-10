import type { AreaEvent, StockLevel } from "./types";

/** Nível de stock de um retângulo: os 3 estados do desafio, ou null quando a câmara não vê ("sem leitura"). */
export type AreaLevel = StockLevel | null;

export type LevelInfo = { level: AreaLevel; minutesAgo: number };

export const LEVEL_TEXT: Record<StockLevel | "none", string> = {
  full: "Cheio",
  half: "Metade",
  empty: "Vazio",
  none: "Sem leitura",
};

/** O nível de cada retângulo, a partir das leituras. */
export function levelsOf(events: AreaEvent[]): Record<string, LevelInfo> {
  const out: Record<string, LevelInfo> = {};
  for (const e of events) out[e.area_id] = { level: e.stock_level, minutesAgo: e.minutes_ago };
  return out;
}

/** O fundo de um retângulo no modo Nível: o azul sobe como num depósito; sem leitura fica às riscas. */
export function levelBackground(level: AreaLevel): string {
  if (level === null) {
    return "repeating-linear-gradient(45deg, var(--color-hatch-a) 0 3px, var(--color-hatch-b) 3px 6px)";
  }
  const pct = level === "full" ? 100 : level === "half" ? 50 : 0;
  return `linear-gradient(to top, var(--color-level-fill) 0 ${pct}%, var(--color-level-base) ${pct}% 100%)`;
}
