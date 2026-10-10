"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Bench } from "@/components/Bench";
import { BottomSheet } from "@/components/BottomSheet";
import { FilterChips, type Filter } from "@/components/FilterChips";
import { Header } from "@/components/Header";
import { UndoBar } from "@/components/UndoBar";
import { WarningRow } from "@/components/WarningRow";
import { cellOf, faceOf, whereOf } from "@/lib/layout";
import { LEVEL_TEXT } from "@/lib/levels";
import { playResolveAnimation, pulseCell } from "@/lib/resolveAnimation";
import type { AreaEvent, Warning } from "@/lib/types";
import { useEvents } from "@/lib/useEvents";
import { buildWarnings, countBySeverity, sortBySeverity } from "@/lib/warnings";

/** Topo do painel de avisos: fechado (12 px abaixo do mapa) e aberto (logo abaixo do cabeçalho). */
const COLLAPSED_TOP = 56 + 480 + 12;
const EXPANDED_TOP = 56 + 12;

/** Ecrã A · Mapa + avisos. */
export default function MapAndWarnings() {
  const { events, levels, refreshing, refresh, resolve, restore } = useEvents();
  const warnings = useMemo(() => sortBySeverity(buildWarnings(events)), [events]);

  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [claimed, setClaimed] = useState<Record<string, boolean>>({});
  const [sheetOpen, setSheetOpen] = useState(false);
  const [mapMode, setMapMode] = useState<"avisos" | "nivel">("avisos"); // abre nos avisos, como antes
  const [inspected, setInspected] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [undo, setUndo] = useState<{ previous: AreaEvent[]; areaId: string; name: string; id: number } | null>(null);
  const undoSeq = useRef(0);
  const expireUndo = useCallback(() => setUndo(null), []);

  const bySeverity = countBySeverity(warnings);
  const counts: Record<Filter, number> = { all: warnings.length, ...bySeverity };
  const shown = filter === "all" ? warnings : warnings.filter((w) => w.severity === filter);

  const toggleSelected = (areaId: string) => setSelected((cur) => (cur === areaId ? null : areaId));
  const toggleClaimed = (areaId: string) => setClaimed((cur) => ({ ...cur, [areaId]: !cur[areaId] }));

  const toggleLevelView = () => {
    setMapMode((m) => (m === "avisos" ? "nivel" : "avisos"));
    setInspected(null);
  };

  /** O que a faixa do painel diz sobre o retângulo tocado no modo Nível. */
  const inspectedText = (() => {
    const cell = inspected ? cellOf(inspected) : undefined;
    if (!cell || !inspected) return null;
    const info = levels[inspected];
    const level = LEVEL_TEXT[info?.level ?? "none"];
    const when = info?.level === null ? `sem imagem há ${info.minutesAgo} min` : `lida há ${info?.minutesAgo ?? 0} min`;
    return `${cell.nome_pt} · ${whereOf(faceOf(cell))} · ${level} · ${when}`;
  })();

  /** Atualizar traz as leituras novas e envelhece as que ficam. Os "A tratar" ficam até serem resolvidos. */
  const onRefresh = async () => {
    const result = await refresh();
    if (!result) return;
    const novos = result.addedIds.length;
    setStatus(`Atualizado: ${novos} ${novos === 1 ? "leitura nova" : "leituras novas"}.`);
  };

  /** Resolvido: a bola viaja até ao mapa, o aviso sai, e há 8 s para desfazer. */
  const onResolve = async (w: Warning, row: HTMLElement | null) => {
    await playResolveAnimation(row, w.area_id);
    const previous = resolve(w.areaIds);
    setClaimed((cur) => {
      const next = { ...cur };
      delete next[w.area_id];
      return next;
    });
    setSelected((cur) => (cur === w.area_id ? null : cur));
    undoSeq.current += 1;
    setUndo({ previous, areaId: w.area_id, name: w.name, id: undoSeq.current });
    setStatus(`${w.name} resolvido.`);
    window.requestAnimationFrame(() => w.areaIds.forEach(pulseCell));
  };

  const onUndo = () => {
    if (!undo) return;
    restore(undo.previous);
    setClaimed((cur) => ({ ...cur, [undo.areaId]: true }));
    setStatus(`${undo.name} reposto.`);
    setUndo(null);
  };

  return (
    <main className="relative mx-auto flex h-dvh w-full max-w-[390px] flex-col overflow-hidden bg-ground text-ink">
      <Header name="Pedro" store="Continente Bom Dia São Romão" refreshing={refreshing}
        onRefresh={onRefresh}
        levelView={mapMode === "nivel"}
        onToggleLevelView={toggleLevelView}
      />
      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>

      <section
        aria-label="Planta da zona de frutas e legumes, vista de cima"
        inert={sheetOpen}
        className="relative h-[480px] flex-none overflow-hidden rounded-b-sheet bg-map"
      >
        <Bench
          warnings={warnings}
          selectedId={selected}
          onSelect={toggleSelected}
          mode={mapMode}
          levels={levels}
          inspectedId={inspected}
          onInspect={setInspected}
        />
      </section>

      <BottomSheet
        ariaLabel="Lista de avisos"
        collapsedTop={COLLAPSED_TOP}
        expandedTop={EXPANDED_TOP}
        expanded={sheetOpen}
        onExpandedChange={setSheetOpen}
      >
        <FilterChips value={filter} counts={counts} onChange={setFilter} />
        <div className="flex-none px-1 pt-2.5 pb-1 text-secondary font-semibold text-ink-secondary">
          {mapMode === "nivel" && inspectedText
            ? inspectedText
            : `${shown.length} ${shown.length === 1 ? "aviso" : "avisos"} · por gravidade e distância`}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pb-6">
          {shown.length === 0 ? (
            <div className="px-2 py-7 text-center text-product font-semibold text-ink-secondary">
              Sem avisos neste nível.
            </div>
          ) : (
            shown.map((w) => (
              <WarningRow
                key={w.area_id}
                warning={w}
                selected={w.area_id === selected}
                claimed={!!claimed[w.area_id]}
                onSelect={() => toggleSelected(w.area_id)}
                onClaim={() => toggleClaimed(w.area_id)}
                onResolve={(row) => onResolve(w, row)}
              />
            ))
          )}
        </div>
      </BottomSheet>
      {undo ? <UndoBar key={undo.id} message={`${undo.name} resolvido`} onUndo={onUndo} onExpire={expireUndo} /> : null}
    </main>
  );
}
