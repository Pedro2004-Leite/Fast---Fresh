"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/components/AppProvider";
import { Bench } from "@/components/Bench";
import { Header } from "@/components/Header";
import { ProgressSegments } from "@/components/ProgressSegments";
import { RoutePath } from "@/components/RoutePath";
import { TaskPanel } from "@/components/TaskPanel";
import { geometry } from "@/lib/layout";
import { fitAll, routeZoom } from "@/lib/mapLayout";
import { routeOf } from "@/lib/route";
import { useElementSize } from "@/lib/useElementSize";
import { buildWarnings, sortBySeverity } from "@/lib/warnings";

/**
 * Ecrã C · Próxima tarefa: só a tarefa pedida, com o mapa aproximado à zona do caminho.
 * Ao fazer (deslizar) ou passar, entra a seguinte.
 */
export default function NextTask() {
  const { events, refreshing, refresh, flow, done, restart: restartApp } = useApp();
  const [skips, setSkips] = useState<Record<string, number>>({});
  const [mapRef, size] = useElementSize<HTMLElement>();

  const warnings = useMemo(() => sortBySeverity(buildWarnings(events)), [events]);
  // "Passar" manda a tarefa para o fim da fila (a ordenação é estável, por isso o resto mantém a ordem).
  const queue = useMemo(
    () => [...warnings].sort((a, b) => (skips[a.area_id] ?? 0) - (skips[b.area_id] ?? 0)),
    [warnings, skips],
  );
  const current = queue[0];
  const total = done + queue.length;

  const pass = () => {
    if (!current) return;
    const farthest = Math.max(0, ...queue.map((w) => skips[w.area_id] ?? 0));
    setSkips((cur) => ({ ...cur, [current.area_id]: farthest + 1 }));
  };

  const restart = () => {
    restartApp();
    setSkips({});
  };

  const onRefresh = async () => {
    const result = await refresh();
    if (!result) return;
    const novos = result.addedIds.length;
    flow.setStatus(`Atualizado: ${novos} ${novos === 1 ? "leitura nova" : "leituras novas"}.`);
  };

  const progressLabel = `${current ? done + 1 : total} de ${total}`;
  const route = current ? routeOf(current.face, current.center) : null;
  const view = current && route ? routeZoom(route, current.center, size.w, size.h) : fitAll(size.w, size.h);

  return (
    <main className="absolute inset-x-0 top-0 bottom-12 flex flex-col overflow-hidden">
      <Header
        name="David"
        store="Continente Bom Dia São Romão"
        refreshing={refreshing}
        onRefresh={onRefresh}
        trailing={
          <span role="status" className="rounded-badge bg-ink px-2.5 py-1 font-mono text-module font-semibold text-ink-on">
            {progressLabel}
          </span>
        }
      />
      <ProgressSegments total={total} done={done} hasCurrent={!!current} label={progressLabel} />

      <section
        ref={mapRef}
        aria-label="Planta da bancada com caminho até ao aviso"
        className="relative min-h-0 flex-1 overflow-hidden rounded-b-sheet bg-map"
      >
        <div
          className="absolute top-0 left-0 origin-top-left motion-safe:transition-transform motion-safe:duration-[450ms] motion-safe:ease-[cubic-bezier(.4,0,.2,1)]"
          style={{
            width: geometry.map.w,
            height: geometry.map.h,
            transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})`,
          }}
        >
          <Bench warnings={queue} selectedId={current?.area_id ?? null} onSelect={() => {}} marks={false}>
            {current && route ? <RoutePath points={route} label={`${current.distanceM} m`} scale={view.scale} /> : null}
          </Bench>
        </div>
      </section>

      <section
        aria-label="Tarefa atual"
        className="flex-none rounded-t-sheet bg-sheet px-gutter pt-3 pb-2.5 shadow-sheet"
      >
        {!current ? (
          <div className="flex flex-col items-center gap-3 px-2 py-3 text-center">
            <span className="flex size-16 items-center justify-center rounded-full bg-ink">
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                className="stroke-ink-on stroke-[2.4]"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </span>
            <h2 className="m-0 text-[24px] font-extrabold">Tudo tratado</h2>
            <p className="m-0 text-button leading-[1.4] font-medium text-ink-secondary">
              Não há avisos ativos. Voltas a ser avisado quando entrar um novo.
            </p>
            <button
              type="button"
              onClick={restart}
              className="m-0 h-button cursor-pointer rounded-full border-2 border-ink bg-transparent px-[22px] text-[15px] font-extrabold text-ink"
            >
              Recomeçar demonstração
            </button>
          </div>
        ) : (
          <TaskPanel
            key={current.area_id}
            warning={current}
            // nesta vista não há "Desfazer": a barra tapava o mapa
            onResolve={(row) => flow.resolveWarning(current, row, { collapse: false })}
            onPass={pass}
            canPass={queue.length > 1}
          />
        )}
      </section>
    </main>
  );
}
