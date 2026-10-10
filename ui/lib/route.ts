import { geometry } from "./layout";
import type { BenchFace, Point } from "./types";

const { user_position: me, aisle_b_x, cross_passage_y, meters_per_px } = geometry;

export function pathLength(points: Point[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    total += Math.abs(points[i].x - points[i - 1].x) + Math.abs(points[i].y - points[i - 1].y);
  }
  return total;
}

/**
 * Caminho a pé em ângulos retos desde o utilizador até ao retângulo (px do mapa).
 * Face A: pelo corredor A. Face B e pontas: contornam a ilha pela passagem do topo ou do fundo
 * (e, na face B, pelo corredor B); usa o caminho mais curto.
 */
export function routeOf(face: BenchFace, target: Point): Point[] {
  const { x: cx, y: cy } = target;
  if (face.side === "A") return [me, { x: me.x, y: cy }, target];
  if (face.side === "end") {
    const y = face.module === 1 ? cross_passage_y.top : cross_passage_y.bottom;
    return [me, { x: me.x, y }, { x: cx, y }, target];
  }
  const via = (y: number): Point[] => [
    me,
    { x: me.x, y },
    { x: aisle_b_x, y },
    { x: aisle_b_x, y: cy },
    target,
  ];
  const top = via(cross_passage_y.top);
  const bottom = via(cross_passage_y.bottom);
  return pathLength(top) <= pathLength(bottom) ? top : bottom;
}

/** Distância a pé em metros (mínimo 1). */
export function distanceOf(face: BenchFace, target: Point): number {
  return Math.max(1, Math.round(pathLength(routeOf(face, target)) * meters_per_px));
}
