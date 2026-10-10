"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/components/AppProvider";
import { Header } from "@/components/Header";
import { SegmentedControl } from "@/components/SegmentedControl";
import { WarningCard } from "@/components/WarningCard";
import { buildWarnings, sortBySeverity } from "@/lib/warnings";

type Sort = "gravidade" | "perto";

/** Ecrã B · Lista + mini-mapa: um cartão por aviso, cada um com a bancada em miniatura. */
export default function WarningList() {
  const { events, refreshing, refresh, flow, showOnMap } = useApp();
  const [sort, setSort] = useState<Sort>("gravidade");

  const warnings = useMemo(() => buildWarnings(events), [events]);
  const list = useMemo(
    () => (sort === "gravidade" ? sortBySeverity(warnings) : [...warnings].sort((a, b) => a.distanceM - b.distanceM)),
    [warnings, sort],
  );
  const critical = warnings.filter((w) => w.severity === "critical").length;

  const onRefresh = async () => {
    const result = await refresh();
    if (!result) return;
    const novos = result.addedIds.length;
    flow.setStatus(`Atualizado: ${novos} ${novos === 1 ? "leitura nova" : "leituras novas"}.`);
  };

  return (
    <main className="absolute inset-x-0 top-0 bottom-12 flex flex-col overflow-hidden">
      <Header name="David" store="Continente Bom Dia São Romão" refreshing={refreshing} onRefresh={onRefresh} />
      <div className="flex flex-none items-end justify-between gap-3 px-gutter pt-1.5 pb-3">
        <div>
          <h1 className="m-0 text-title-b font-extrabold tracking-[-0.02em]">Avisos</h1>
          <div className="mt-1 text-button font-semibold text-ink-secondary">
            {warnings.length} {warnings.length === 1 ? "aviso ativo" : "avisos ativos"} · {critical}{" "}
            {critical === 1 ? "crítico" : "críticos"}
          </div>
        </div>
      </div>

      <div className="flex-none px-gutter">
        <SegmentedControl
          ariaLabel="Ordenar avisos"
          value={sort}
          onChange={setSort}
          options={[
            { value: "gravidade", label: "Gravidade" },
            { value: "perto", label: "Mais perto" },
          ]}
        />
      </div>

      <div
        className={`flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-gutter pt-3.5 pb-7`}
      >
        {list.length === 0 ? (
          <div className="px-2 py-10 text-center text-product font-semibold text-ink-secondary">Sem avisos ativos.</div>
        ) : (
          list.map((w) => (
            <WarningCard
              key={w.area_id}
              warning={w}
              claimed={!!flow.claimed[w.area_id]}
              onClaim={() => flow.toggleClaimed(w.area_id)}
              onResolve={(row) => flow.resolveWarning(w, row)}
              onShowOnMap={() => showOnMap(w.area_id)}
            />
          ))
        )}
      </div>

    </main>
  );
}
