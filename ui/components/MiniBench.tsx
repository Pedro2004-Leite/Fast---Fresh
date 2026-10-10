import { geometry, layout } from "@/lib/layout";
import type { Warning } from "@/lib/types";
import { SEVERITY_BG } from "./SeverityBadge";

const W = 108;
const H = 117;
const MARGIN = 6;
/** A bancada reduzida a 96 px de largura (6 px de margem de cada lado), centrada no módulo do aviso. */
const SCALE = (W - MARGIN * 2) / geometry.island.w;

/** O meio vertical do módulo (px, relativos ao canto da ilha): faces e barra do módulo. */
function moduleMiddle(module: number): number {
  const rects = [
    ...layout.faces.filter((f) => f.module === module).map((f) => f.rect),
    ...layout.spines.filter((s) => s.module === module).map((s) => s.rect),
  ];
  const top = Math.min(...rects.map((r) => r.y));
  const bottom = Math.max(...rects.map((r) => r.y + r.h));
  return (top + bottom) / 2;
}

/**
 * A bancada em miniatura, centrada no módulo do aviso. Os retângulos do aviso ficam da cor da gravidade
 * e com contorno; as barras escuras são as do mapa.
 */
export function MiniBench({ warning, label }: { warning: Warning; label: string }) {
  const translateY = H / 2 - moduleMiddle(warning.face.module) * SCALE;
  const ids = new Set(warning.areaIds);

  return (
    <div
      role="img"
      aria-label={label}
      className="relative flex-none overflow-hidden rounded-badge bg-map"
      style={{ width: W, height: H }}
    >
      <div
        className="absolute top-0 left-0 origin-top-left"
        style={{
          width: geometry.island.w,
          height: geometry.island.h,
          transform: `translate(${MARGIN}px, ${translateY}px) scale(${SCALE})`,
        }}
      >
        {layout.cells.map((cell) => {
          const mine = ids.has(cell.area_id);
          return (
            <div
              key={cell.area_id}
              className={`absolute box-border rounded-cell ${mine ? SEVERITY_BG[warning.severity] : "bg-cell"} ${
                mine ? "z-[2] outline-[3px] outline-offset-2 outline-ink" : ""
              }`}
              style={{ left: cell.rect.x, top: cell.rect.y, width: cell.rect.w, height: cell.rect.h }}
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
    </div>
  );
}
