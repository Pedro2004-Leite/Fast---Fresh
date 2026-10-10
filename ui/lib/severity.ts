import type { AlertKind, AreaEvent, Severity } from "./types";

/** Ordem de gravidade: maior = mais grave. */
export const SEVERITY_RANK: Record<Severity, number> = { critical: 3, high: 2, medium: 1 };

export const SEVERITY_LABEL: Record<Severity, { word: string; label: string }> = {
  critical: { word: "CRÍTICO", label: "Crítico" },
  high: { word: "ALTO", label: "Alto" },
  medium: { word: "MÉDIO", label: "Médio" },
};

/** Sem imagem há mais do que isto (minutos), a câmara dá um aviso. */
export const BLIND_AFTER_MINUTES = 30;

export type Alert = { severity: Severity; kind: AlertKind; task: string };

/**
 * A regra de gravidade (aprovada no Lavish), uma só para os três ecrãs:
 * - produto errado: crítico, vai para o topo da lista;
 * - vazio: crítico (Repor);
 * - reclamação com o prateleira a metade ou cheia: alto (Repor / Verificar);
 * - câmara sem imagem há mais de 30 min: médio (Verificar a câmara);
 * - metade ou cheio, sem reclamação: sem aviso (a metade só se vê no modo Nível).
 */
export function alertOf(event: AreaEvent): Alert | null {
  if (!event.planogram_compliant) return { severity: "critical", kind: "wrong", task: "Produto errado" };
  if (event.stock_level === "empty") return { severity: "critical", kind: "empty", task: "Repor" };
  if (event.complaint) {
    return { severity: "high", kind: "complaint", task: event.stock_level === "half" ? "Repor" : "Verificar" };
  }
  if (event.stock_level === null && event.minutes_ago > BLIND_AFTER_MINUTES) {
    return { severity: "medium", kind: "blind", task: "Verificar a câmara" };
  }
  return null;
}
