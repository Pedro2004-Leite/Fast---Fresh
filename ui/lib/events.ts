import { layout } from "./layout";
import type { AreaEvent, StockLevel } from "./types";

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** Leituras de exemplo (mock) que contam a história do demo; o resto da bancada vem de `getSampleEvents`. */
const DEMO: AreaEvent[] = [
  { area_id: "6468_5", stock_level: "empty", planogram_compliant: true, complaint: null, minutes_ago: 1 },
  { area_id: "6443_3", stock_level: "empty", planogram_compliant: true, complaint: "Tomate cherry esgotado", minutes_ago: 2 },
  { area_id: "6373_1", stock_level: "empty", planogram_compliant: true, complaint: null, minutes_ago: 4 },
  { area_id: "6591_3", stock_level: "half", planogram_compliant: true, complaint: "Preço errado na etiqueta", minutes_ago: 6 },
  { area_id: "6371_2", stock_level: "full", planogram_compliant: false, complaint: null, minutes_ago: 3 },
  { area_id: "6215_1", stock_level: "half", planogram_compliant: true, complaint: null, minutes_ago: 9 },
  { area_id: "6594_3", stock_level: "half", planogram_compliant: true, complaint: null, minutes_ago: 12 },
];

/**
 * Leituras de exemplo (mock) dos 56 retângulos: sempre as mesmas. A câmara 6383 está sem imagem há 41 min
 * (cabine fechada). Em dados reais isto vem do servidor (stock_level e planogram_compliant por area_id).
 */
export function getSampleEvents(): AreaEvent[] {
  const events: AreaEvent[] = layout.cells.map((cell) => {
    const h = hash(cell.area_id);
    const r = h % 100;
    const level: StockLevel = r < 60 ? "full" : r < 96 ? "half" : "empty";
    return {
      area_id: cell.area_id,
      stock_level: cell.camera_id === "6383" ? null : level,
      planogram_compliant: true,
      complaint: null,
      minutes_ago: cell.camera_id === "6383" ? 41 : 1 + ((h >>> 8) % 9),
    };
  });
  const demo = new Map(DEMO.map((e) => [e.area_id, e]));
  return events.map((e) => demo.get(e.area_id) ?? e);
}

/** Leituras novas de exemplo (mock): cada atualização traz o lote seguinte, até acabarem. */
export const INCOMING_BATCHES: AreaEvent[][] = [
  [
    { area_id: "6376_2", stock_level: "empty", planogram_compliant: true, complaint: null, minutes_ago: 1 },
    { area_id: "6462_3", stock_level: "half", planogram_compliant: true, complaint: "Uvas moles", minutes_ago: 2 },
  ],
  [
    { area_id: "6443_1", stock_level: "full", planogram_compliant: false, complaint: null, minutes_ago: 1 },
    { area_id: "6594_1", stock_level: "empty", planogram_compliant: true, complaint: null, minutes_ago: 3 },
  ],
  [{ area_id: "6781_2", stock_level: "empty", planogram_compliant: true, complaint: null, minutes_ago: 1 }],
];

/** Minutos que passam, em média, entre duas atualizações (as leituras que ficam envelhecem outro tanto). */
export const MINUTES_BETWEEN_REFRESHES = 2;

export type RefreshResult = {
  events: AreaEvent[];
  addedIds: string[];
};

/**
 * O que a atualização faz: as leituras novas substituem as antigas da mesma área, e as que ficam envelhecem.
 * Os "A tratar" ficam até serem resolvidos (isso não depende da atualização).
 */
export function applyRefresh(
  events: AreaEvent[],
  incoming: AreaEvent[],
  elapsedMinutes: number = MINUTES_BETWEEN_REFRESHES,
): RefreshResult {
  const fresh = new Map(incoming.map((e) => [e.area_id, e]));
  return {
    events: events.map((e) => fresh.get(e.area_id) ?? { ...e, minutes_ago: e.minutes_ago + elapsedMinutes }),
    addedIds: incoming.map((e) => e.area_id),
  };
}

/**
 * A leitura depois de resolver: o que estava vazio, com reclamação ou sem imagem fica cheio (foi reposto ou a
 * câmara voltou a ver); o produto arrumado fica conforme, com o stock que tinha.
 */
export function resolvedReading(event: AreaEvent): AreaEvent {
  const restocked = event.stock_level === null || event.stock_level === "empty" || !!event.complaint;
  return {
    ...event,
    stock_level: restocked ? "full" : event.stock_level,
    planogram_compliant: true,
    complaint: null,
    minutes_ago: 0,
  };
}

/** Dá as áreas como resolvidas. Devolve as leituras de antes, para poder desfazer. */
export function resolveReadings(events: AreaEvent[], areaIds: string[]): { events: AreaEvent[]; previous: AreaEvent[] } {
  const ids = new Set(areaIds);
  return {
    events: events.map((e) => (ids.has(e.area_id) ? resolvedReading(e) : e)),
    previous: events.filter((e) => ids.has(e.area_id)),
  };
}

/** Desfaz um "resolvido": volta a pôr as leituras de antes. */
export function restoreReadings(events: AreaEvent[], previous: AreaEvent[]): AreaEvent[] {
  const back = new Map(previous.map((e) => [e.area_id, e]));
  return events.map((e) => back.get(e.area_id) ?? e);
}
