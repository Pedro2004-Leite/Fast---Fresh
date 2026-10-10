import type { MouseEvent } from "react";
import { LevelLegend } from "@/components/LevelLegend";
import { SEVERITY_BG } from "@/components/SeverityBadge";
import { SEVERITY_LABEL } from "@/lib/severity";
import { cellAtPoint, geometry, layout, whereOf } from "@/lib/layout";
import { warningsByArea } from "@/lib/warnings";
import { levelBackground, LEVEL_TEXT, type LevelInfo } from "@/lib/levels";
import type { Warning } from "@/lib/types";

type Props = {
  warnings: Warning[];
  selectedId: string | null;
  onSelect: (areaId: string) => void;
  /** "avisos": cor da gravidade nos retângulos com aviso. "nivel": o nível de stock de todos (os avisos ficam escondidos). */
  mode: "avisos" | "nivel";
  levels: Record<string, LevelInfo>;
  inspectedId: string | null;
  onInspect: (areaId: string) => void;
};

/**
 * A planta da bancada vista de cima, no mapa de 390 x 480 px. Um retângulo por area_id, em px inteiros,
 * sem linhas nem rebordos. O retângulo com aviso fica da cor da gravidade; o crítico pulsa; o selecionado
 * tem contorno de 2 px. Botões de toque transparentes de 44 x 44 px sobre os retângulos com aviso.
 */
export function Bench({ warnings, selectedId, onSelect, mode, levels, inspectedId, onInspect }: Props) {
  const byArea = warningsByArea(warnings);
  const { island, user_position: me, map } = geometry;
  const level = mode === "nivel";

  /** No modo Nível o toque escolhe o retângulo mais perto (sem botões de 44 px a sobrepor-se). */
  const inspectAt = (e: MouseEvent<HTMLDivElement>) => {
    if (!level) return;
    const box = e.currentTarget.getBoundingClientRect();
    const cell = cellAtPoint(e.clientX - box.left - island.x, e.clientY - box.top - island.y);
    if (cell) onInspect(cell.area_id);
  };

  return (
    <div data-bench onClick={inspectAt} className="relative mx-auto" style={{ width: map.w, height: map.h }}>
      <div
        role="img"
        aria-label={`Bancada de frutas e legumes: ${layout.spines.length} módulos, ${layout.cells.length} produtos`}
        className="absolute"
        style={{ left: island.x, top: island.y, width: island.w, height: island.h }}
      >
        {layout.cells.map((cell) => {
          const warning = byArea.get(cell.area_id);
          const rect = { left: cell.rect.x, top: cell.rect.y, width: cell.rect.w, height: cell.rect.h };
          if (level) {
            const inspected = cell.area_id === inspectedId;
            return (
              <div
                key={cell.area_id}
                data-cell={cell.area_id}
                className={`absolute box-border rounded-cell ${inspected ? "z-[2] outline-2 outline-offset-2 outline-ink" : ""}`}
                style={{ ...rect, background: levelBackground(levels[cell.area_id]?.level ?? null) }}
              />
            );
          }
          const selected = !!warning && warning.area_id === selectedId;
          const color = warning ? SEVERITY_BG[warning.severity] : "bg-cell";
          const pulse = warning?.severity === "critical" ? "animate-ring" : "";
          const marked = warning ? (selected ? "z-[2] outline-2 outline-offset-2 outline-ink" : "z-[1]") : "";
          return (
            <div
              key={cell.area_id}
              data-cell={cell.area_id}
              className={`absolute box-border rounded-cell ${color} ${pulse} ${marked}`}
              style={rect}
            />
          );
        })}
        {layout.spines.map((spine) => (
          <div
            key={spine.module}
            className="absolute box-border flex items-center justify-center rounded-cell bg-bar font-mono text-module font-semibold text-bar-ink"
            style={{ left: spine.rect.x, top: spine.rect.y, width: spine.rect.w, height: spine.rect.h }}
          >
            {spine.module}
          </div>
        ))}
      </div>

      {(level ? [] : warnings).map((w) => {
        const selected = w.area_id === selectedId;
        return (
          <button
            key={w.area_id}
            type="button"
            onClick={() => onSelect(w.area_id)}
            aria-label={`${w.name}, ${whereOf(w.face).toLowerCase()}, ${SEVERITY_LABEL[w.severity].label.toLowerCase()}`}
            aria-pressed={selected}
            className="absolute z-[3] m-0 size-touch cursor-pointer border-0 bg-transparent p-0"
            style={{ left: Math.round(w.center.x - 22), top: Math.round(w.center.y - 22) }}
          />
        );
      })}

      {level ? <LevelLegend /> : null}
      {level ? (
        <ul className="sr-only" aria-label="Nível de stock de cada produto">
          {layout.cells.map((cell) => (
            <li key={cell.area_id}>
              {cell.nome_pt}, {whereOf(layout.faces.find((f) => f.module === cell.module && f.side === cell.side)!).toLowerCase()}:{" "}
              {LEVEL_TEXT[levels[cell.area_id]?.level ?? "none"].toLowerCase()}
            </li>
          ))}
        </ul>
      ) : null}

      <div
        role="img"
        aria-label="A tua posição, corredor A"
        className="absolute z-[6] size-0"
        style={{ left: me.x, top: me.y }}
      >
        <span className="absolute -top-[15px] -left-[15px] size-[30px] animate-user-pulse rounded-full bg-ink" />
        <span className="absolute -top-[13px] -left-[13px] box-border flex size-[26px] items-center justify-center rounded-full border-2 border-map bg-ink text-mono-id font-extrabold text-white shadow-[0_0_0_2px_var(--color-ink)]">
          Tu
        </span>
      </div>
    </div>
  );
}
