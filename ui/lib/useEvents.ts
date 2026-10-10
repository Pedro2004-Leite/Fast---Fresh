"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyRefresh,
  getSampleEvents,
  INCOMING_BATCHES,
  resolveReadings,
  type RefreshResult,
} from "./events";
import { levelsOf, type LevelInfo } from "./levels";
import type { AreaEvent } from "./types";

/** Tempo simulado do pedido de atualização (ms). */
const MOCK_LATENCY_MS = 700;

export type UseEvents = {
  /** A leitura de cada um dos 56 retângulos. */
  events: AreaEvent[];
  /** O nível de cada retângulo (para o modo Nível do mapa). */
  levels: Record<string, LevelInfo>;
  refreshing: boolean;
  /** Traz as leituras novas e envelhece as que ficam. Ignora toques enquanto já está a atualizar. */
  refresh: () => Promise<RefreshResult | null>;
  /** Dá as áreas como resolvidas (definitivo). */
  resolve: (areaIds: string[]) => void;
  /** Volta aos dados do início (recomeçar a demonstração). */
  reset: () => void;
};

/**
 * Fonte das leituras (area_id, stock_level, planogram_compliant, complaint?). Hoje usa dados de exemplo;
 * para dados reais, troca o corpo de `refresh` (e o estado inicial) por pedidos ao servidor,
 * mantendo o mesmo tipo de retorno.
 */
export function useEvents(): UseEvents {
  const [events, setEvents] = useState<AreaEvent[]>(getSampleEvents);
  const [refreshing, setRefreshing] = useState(false);
  const busy = useRef(false);
  const nextBatch = useRef(0);
  const current = useRef(events);
  useEffect(() => {
    current.current = events;
  }, [events]);

  const refresh = useCallback(async () => {
    if (busy.current) return null;
    busy.current = true;
    setRefreshing(true);
    try {
      await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MS));
      const incoming = INCOMING_BATCHES[nextBatch.current] ?? [];
      nextBatch.current += 1;
      const result = applyRefresh(current.current, incoming);
      setEvents(result.events);
      return result;
    } finally {
      busy.current = false;
      setRefreshing(false);
    }
  }, []);

  const resolve = useCallback((areaIds: string[]) => {
    setEvents(resolveReadings(current.current, areaIds));
  }, []);

  const reset = useCallback(() => {
    nextBatch.current = 0;
    setEvents(getSampleEvents());
  }, []);

  const levels = useMemo(() => levelsOf(events), [events]);

  return { events, levels, refreshing, refresh, resolve, reset };
}
