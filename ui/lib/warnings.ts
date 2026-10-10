import { cellOf, faceOf, geometry } from "./layout";
import { distanceOf } from "./route";
import { alertOf, SEVERITY_RANK } from "./severity";
import type { AreaEvent, Point, Severity, Warning } from "./types";

/**
 * Leituras com aviso, localizadas na bancada. Uma câmara sem imagem é UM aviso, para todos os seus retângulos
 * (cinco retângulos às riscas são um problema, não cinco). Áreas desconhecidas ficam de fora.
 */
export function buildWarnings(events: AreaEvent[]): Warning[] {
  const warnings: Warning[] = [];
  const blindByCamera = new Map<string, AreaEvent[]>();

  for (const event of events) {
    const alert = alertOf(event);
    if (!alert) continue;
    const cell = cellOf(event.area_id);
    if (!cell) {
      console.warn(`area_id desconhecido na bancada: ${event.area_id}`);
      continue;
    }
    if (alert.kind === "blind") {
      blindByCamera.set(cell.camera_id, [...(blindByCamera.get(cell.camera_id) ?? []), event]);
      continue;
    }
    const face = faceOf(cell);
    const center = { x: geometry.island.x + cell.rect.x + cell.rect.w / 2, y: geometry.island.y + cell.rect.y + cell.rect.h / 2 };
    warnings.push({
      event,
      area_id: event.area_id,
      areaIds: [event.area_id],
      kind: alert.kind,
      task: alert.task,
      name: cell.nome_pt,
      face,
      severity: alert.severity,
      distanceM: distanceOf(face, center),
      center,
    });
  }

  for (const [camera, group] of blindByCamera) {
    const cells = group.map((e) => cellOf(e.area_id)!);
    const first = cells[0];
    const face = faceOf(first);
    const points: Point[] = cells.map((c) => ({
      x: geometry.island.x + c.rect.x + c.rect.w / 2,
      y: geometry.island.y + c.rect.y + c.rect.h / 2,
    }));
    const center = {
      x: points.reduce((s, p) => s + p.x, 0) / points.length,
      y: points.reduce((s, p) => s + p.y, 0) / points.length,
    };
    warnings.push({
      event: group[0],
      area_id: first.area_id,
      areaIds: cells.map((c) => c.area_id),
      kind: "blind",
      task: "Verificar a câmara",
      name: `Câmara ${camera} sem imagem`,
      face,
      severity: "medium",
      distanceM: distanceOf(face, center),
      center,
    });
  }
  return warnings;
}

/** Produto errado no topo; depois gravidade (decrescente) e distância (crescente). */
export function sortBySeverity(warnings: Warning[]): Warning[] {
  const top = (w: Warning) => (w.kind === "wrong" ? 1 : 0);
  return [...warnings].sort(
    (a, b) =>
      top(b) - top(a) || SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || a.distanceM - b.distanceM,
  );
}

export function countBySeverity(warnings: Warning[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0 };
  for (const w of warnings) counts[w.severity] += 1;
  return counts;
}

/** O retângulo é de algum aviso? (para o mapa). */
export function warningsByArea(warnings: Warning[]): Map<string, Warning> {
  const out = new Map<string, Warning>();
  for (const w of warnings) for (const id of w.areaIds) out.set(id, w);
  return out;
}
