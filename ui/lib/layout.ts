import benchLayout from "../data/bench-layout.json";
import type { BenchCell, BenchFace, BenchLayout, Point } from "./types";

export const layout = benchLayout as unknown as BenchLayout;

export const { geometry } = layout;

const cellById = new Map(layout.cells.map((c) => [c.area_id, c]));

export function cellOf(areaId: string): BenchCell | undefined {
  return cellById.get(areaId);
}

export function faceOf(cell: BenchCell): BenchFace {
  const face = layout.faces.find((f) => f.module === cell.module && f.side === cell.side);
  if (!face) throw new Error(`Sem face para o módulo ${cell.module} / ${cell.side}`);
  return face;
}

/** Centro do retângulo em px do mapa (a ilha está deslocada no mapa). */
export function cellCenter(cell: BenchCell): Point {
  return {
    x: geometry.island.x + cell.rect.x + cell.rect.w / 2,
    y: geometry.island.y + cell.rect.y + cell.rect.h / 2,
  };
}

export function whereOf(face: BenchFace): string {
  return `Módulo ${face.module}` + (face.side === "end" ? " · Ponta" : ` · Corredor ${face.side}`);
}

/**
 * O retângulo tocado: o que contém o ponto (px relativos ao canto da ilha) ou, se o toque cair no espaço
 * entre retângulos, o mais próximo a menos de `slop` px. Assim o toque é generoso sem botões a sobrepor-se.
 */
export function cellAtPoint(x: number, y: number, slop = 22): BenchCell | undefined {
  let best: BenchCell | undefined;
  let bestDistance = Infinity;
  for (const cell of layout.cells) {
    const { x: rx, y: ry, w, h } = cell.rect;
    const dx = Math.max(rx - x, 0, x - (rx + w));
    const dy = Math.max(ry - y, 0, y - (ry + h));
    const distance = Math.hypot(dx, dy);
    if (distance < bestDistance) {
      best = cell;
      bestDistance = distance;
    }
  }
  return bestDistance <= slop ? best : undefined;
}
