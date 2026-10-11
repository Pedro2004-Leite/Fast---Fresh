"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppProvider";
import { Bench } from "@/components/Bench";
import { Header } from "@/components/Header";
import { CameraShot } from "@/components/CameraShot";
import { LevelLegend } from "@/components/LevelLegend";
import { MapTaskCard } from "@/components/MapTaskCard";
import { SHOTS } from "@/lib/cameraShots";
import { cellOf, faceOf, whereOf } from "@/lib/layout";
import { LEVEL_TEXT } from "@/lib/levels";
import { HEADER_H, mapLayout, STRIP_H } from "@/lib/mapLayout";
import { geometry } from "@/lib/layout";
import { useElementSize } from "@/lib/useElementSize";
import { buildWarnings, sortBySeverity } from "@/lib/warnings";

/** Ecrã A · Mapa: só o mapa. Tocar num aviso encolhe o mapa e abre a tarefa no sítio da barra de separadores. */
export default function MapView() {
  const { events, levels, refreshing, refresh, flow, setNavHidden, pendingSelect, clearPendingSelect } = useApp();
  const warnings = useMemo(() => sortBySeverity(buildWarnings(events)), [events]);

  const [selected, setSelected] = useState<string | null>(null);
  const [mapMode, setMapMode] = useState<"avisos" | "nivel">("avisos"); // abre nos avisos
  const [inspected, setInspected] = useState<string | null>(null);
  const [cardHeight, setCardHeight] = useState(176);
  const [mainRef, frame] = useElementSize<HTMLElement>({ w: 390, h: 844 });

  // Se o aviso selecionado saiu (resolvido), a seleção deixa de valer.
  const selectedWarning = warnings.find((w) => w.area_id === selected) ?? null;
  const inspectedCell = mapMode === "nivel" && inspected ? cellOf(inspected) : undefined;
  const open = mapMode === "avisos" ? !!selectedWarning : !!inspectedCell;
  // A foto da câmara do aviso (se a demonstração a tiver): o mapa encosta à esquerda e a foto aparece à direita.
  const shot = mapMode === "avisos" && selectedWarning ? SHOTS[selectedWarning.area_id] : undefined;

  useEffect(() => {
    setNavHidden(open);
    return () => setNavHidden(false);
  }, [open, setNavHidden]);

  // Vindo da Lista ("Ver no mapa"): o mapa aparece inteiro e, dois quadros depois, seleciona o aviso,
  // para a animação ser a mesma de quando se toca num retângulo (o mapa encolhe e a tarefa sobe).
  useEffect(() => {
    if (!pendingSelect) return;
    const id = pendingSelect;
    let second = 0;
    const first = window.requestAnimationFrame(() => {
      second = window.requestAnimationFrame(() => {
        setSelected(id);
        clearPendingSelect();
      });
    });
    return () => {
      window.cancelAnimationFrame(first);
      window.cancelAnimationFrame(second);
    };
  }, [pendingSelect, clearPendingSelect]);

  const critical = warnings.filter((w) => w.severity === "critical").length;
  const layout = mapLayout(frame.h, cardHeight, open, frame.w, !!shot);

  const toggleLevelView = () => {
    setMapMode((m) => (m === "avisos" ? "nivel" : "avisos"));
    setInspected(null);
    setSelected(null);
  };

  const onRefresh = async () => {
    const result = await refresh();
    if (!result) return;
    const novos = result.addedIds.length;
    flow.setStatus(`Atualizado: ${novos} ${novos === 1 ? "leitura nova" : "leituras novas"}.`);
  };

  const onHeight = useCallback((h: number) => setCardHeight(h), []);

  let content: Parameters<typeof MapTaskCard>[0]["content"] = null;
  if (mapMode === "avisos" && selectedWarning) {
    const w = selectedWarning;
    content = {
      kind: "warning",
      warning: w,
      claimed: !!flow.claimed[w.area_id],
      onClaim: () => flow.toggleClaimed(w.area_id),
      // o cartão desliza para baixo por si: aqui só esmaece
      onResolve: (row) => flow.resolveWarning(w, row, { collapse: false }),
    };
  } else if (inspectedCell && inspected) {
    const info = levels[inspected];
    content = {
      kind: "info",
      title: inspectedCell.nome_pt,
      where: whereOf(faceOf(inspectedCell)),
      lines: [
        LEVEL_TEXT[info?.level ?? "none"],
        info?.level === null ? `sem imagem há ${info.minutesAgo} min` : `lida há ${info?.minutesAgo ?? 0} min`,
      ],
    };
  }

  const close = () => {
    setSelected(null);
    setInspected(null);
  };

  return (
    <main ref={mainRef} className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-x-0 top-0">
        <Header
          name="David"
          store="Continente Bom Dia São Romão"
          refreshing={refreshing}
          onRefresh={onRefresh}
          levelView={mapMode === "nivel"}
          onToggleLevelView={toggleLevelView}
        />
      </div>

      {/* A faixa do contador (ou da legenda): fica separada do mapa. */}
      <div className="absolute inset-x-0 flex items-center px-gutter" style={{ top: HEADER_H, height: STRIP_H }}>
        {mapMode === "nivel" ? (
          <LevelLegend />
        ) : (
          <span className="rounded-full bg-ink px-3 py-1.5 text-secondary font-extrabold text-ink-on">
            {warnings.length} {warnings.length === 1 ? "aviso" : "avisos"} · {critical} {critical === 1 ? "crítico" : "críticos"}
          </span>
        )}
      </div>

      <section
        aria-label="Planta da zona de frutas e legumes, vista de cima"
        onClick={(e) => {
          if (e.target === e.currentTarget) close(); // tocar no espaço vazio à volta do mapa
        }}
        className="absolute left-0 overflow-hidden rounded-b-sheet bg-map motion-safe:transition-[bottom,width] motion-safe:duration-[380ms] motion-safe:ease-[cubic-bezier(.4,0,.2,1)]"
        style={{ top: HEADER_H + STRIP_H, bottom: layout.bottomOffset, width: layout.width }}
      >
        <div
          className="absolute top-0 left-0 origin-top-left motion-safe:transition-transform motion-safe:duration-[380ms] motion-safe:ease-[cubic-bezier(.4,0,.2,1)]"
          style={{
            width: geometry.map.w,
            height: geometry.map.h,
            transform: `translate(${layout.left}px, ${layout.top}px) scale(${layout.scale})`,
          }}
        >
          <Bench
            warnings={warnings}
            selectedId={selectedWarning?.area_id ?? null}
            onSelect={setSelected}
            onClear={close}
            mode={mapMode}
            levels={levels}
            inspectedId={inspected}
            onInspect={setInspected}
            scale={layout.scale}
            showUser={!shot}
          />
        </div>
      </section>

      {shot && selectedWarning ? <CameraShot key={selectedWarning.area_id} shot={shot} warning={selectedWarning} /> : null}

      <MapTaskCard open={open} onClose={close} onHeight={onHeight} content={content} />
    </main>
  );
}
