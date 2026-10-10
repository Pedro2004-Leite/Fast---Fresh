import { describe, expect, it } from "vitest";
import { getSampleEvents } from "../events";
import { cellOf, layout } from "../layout";
import { alertOf, BLIND_AFTER_MINUTES } from "../severity";
import type { AreaEvent } from "../types";
import { buildWarnings, sortBySeverity, warningsByArea } from "../warnings";

const ev = (over: Partial<AreaEvent> = {}): AreaEvent => ({
  area_id: "6373_1",
  stock_level: "full",
  planogram_compliant: true,
  complaint: null,
  minutes_ago: 5,
  ...over,
});

describe("regra de gravidade (aprovada no Lavish)", () => {
  it("produto errado é crítico, mesmo com stock cheio", () => {
    expect(alertOf(ev({ planogram_compliant: false }))).toMatchObject({ severity: "critical", kind: "wrong", task: "Produto errado" });
    expect(alertOf(ev({ planogram_compliant: false, stock_level: "empty" }))?.kind).toBe("wrong");
  });

  it("vazio é crítico: Repor", () => {
    expect(alertOf(ev({ stock_level: "empty" }))).toMatchObject({ severity: "critical", kind: "empty", task: "Repor" });
    expect(alertOf(ev({ stock_level: "empty", complaint: "x" }))?.severity).toBe("critical");
  });

  it("reclamação sobe a gravidade: alto (Repor a metade, Verificar cheio)", () => {
    expect(alertOf(ev({ stock_level: "half", complaint: "x" }))).toMatchObject({ severity: "high", task: "Repor" });
    expect(alertOf(ev({ stock_level: "full", complaint: "x" }))).toMatchObject({ severity: "high", task: "Verificar" });
  });

  it("metade ou cheio sem reclamação não dão aviso (a metade só se vê no modo Nível)", () => {
    expect(alertOf(ev({ stock_level: "half" }))).toBeNull();
    expect(alertOf(ev({ stock_level: "full" }))).toBeNull();
  });

  it("câmara sem imagem há mais de 30 min: médio, Verificar a câmara", () => {
    expect(alertOf(ev({ stock_level: null, minutes_ago: BLIND_AFTER_MINUTES }))).toBeNull();
    expect(alertOf(ev({ stock_level: null, minutes_ago: BLIND_AFTER_MINUTES + 1 }))).toMatchObject({
      severity: "medium",
      kind: "blind",
      task: "Verificar a câmara",
    });
  });
});

describe("avisos", () => {
  it("distâncias a pé dos retângulos de exemplo: 11, 22, 6, 21, 10 e 23 m", () => {
    // O README (planta original) dá 12, 22, 6, 22, 11 e 23 m. Com a bancada de 154 px e as pontas viradas para o meio,
    // os retângulos das pontas ficam mais perto da passagem (11 e 10 m) e o 4.º passa de 21,51 m para 21,48 m (21).
    const ids = ["6468_5", "6443_3", "6373_1", "6591_3", "6215_1", "6594_3"];
    const warnings = buildWarnings(ids.map((id) => ev({ area_id: id, stock_level: "empty" })));
    expect(warnings.map((w) => w.distanceM)).toEqual([11, 22, 6, 21, 10, 23]);
  });

  it("uma câmara sem imagem é UM aviso, para todos os seus retângulos", () => {
    const blind = layout.cells.filter((c) => c.camera_id === "6383").map((c) => ev({ area_id: c.area_id, stock_level: null, minutes_ago: 41 }));
    expect(blind).toHaveLength(5);
    const warnings = buildWarnings(blind);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatchObject({ kind: "blind", severity: "medium", name: "Câmara 6383 sem imagem" });
    expect(warnings[0].areaIds).toHaveLength(5);
    // o mapa pinta os 5 retângulos com o mesmo aviso
    const byArea = warningsByArea(warnings);
    for (const id of warnings[0].areaIds) expect(byArea.get(id)).toBe(warnings[0]);
  });

  it("produto errado vai sempre para o topo; depois gravidade e distância", () => {
    const warnings = buildWarnings([
      ev({ area_id: "6373_1", stock_level: "full", complaint: "x" }), // alto
      ev({ area_id: "6468_5", stock_level: "empty" }), // crítico
      ev({ area_id: "6371_2", planogram_compliant: false }), // produto errado
      ev({ area_id: "6443_3", stock_level: "empty" }), // crítico
    ]);
    const order = sortBySeverity(warnings).map((w) => w.area_id);
    expect(order[0]).toBe("6371_2");
    expect(order.at(-1)).toBe("6373_1");
    expect(order.indexOf("6468_5")).toBeLessThan(order.indexOf("6443_3")); // 11 m antes de 22 m
  });

  it("os dados de exemplo contam a história do demo", () => {
    const events = getSampleEvents();
    expect(events).toHaveLength(56);
    const warnings = sortBySeverity(buildWarnings(events));
    expect(warnings[0]).toMatchObject({ area_id: "6371_2", kind: "wrong" }); // Melancia no topo
    const by = (id: string) => warnings.find((w) => w.areaIds.includes(id));
    expect(by("6468_5")?.severity).toBe("critical"); // Banana vazia
    expect(by("6443_3")?.severity).toBe("critical"); // Tomate cherry vazio
    expect(by("6591_3")?.severity).toBe("high"); // Batata, metade com reclamação
    expect(by("6383_1")?.kind).toBe("blind");
    expect(warnings.filter((w) => w.kind === "blind")).toHaveLength(1);
    // sem avisos para metade nem cheio sem reclamação
    expect(by("6215_1")).toBeUndefined();
    expect(new Set(warnings.map((w) => w.area_id)).size).toBe(warnings.length);
    expect(cellOf("6371_2")?.nome_pt).toBe("Melancia");
  });
});

describe("bancada", () => {
  it("56 retângulos com area_id únicos e posições em px inteiros", () => {
    expect(layout.cells).toHaveLength(56);
    expect(new Set(layout.cells.map((c) => c.area_id)).size).toBe(56);
    for (const c of layout.cells) {
      for (const v of Object.values(c.rect)) expect(Number.isInteger(v)).toBe(true);
    }
  });
});

describe("geometria da bancada", () => {
  const rects = [
    ...layout.cells.map((c) => ({ id: c.area_id, ...c.rect })),
    ...layout.spines.map((s) => ({ id: `módulo ${s.module}`, ...s.rect })),
  ];

  it("nada se sobrepõe nem sai da ilha", () => {
    const { island } = layout.geometry;
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(0);
      expect(r.y).toBeGreaterThanOrEqual(0);
      expect(r.x + r.w).toBeLessThanOrEqual(island.w);
      expect(r.y + r.h).toBeLessThanOrEqual(island.h);
    }
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        expect(overlap, `${a.id} sobrepõe-se a ${b.id}`).toBe(false);
      }
    }
  });
});

describe("bancada: pontas a atravessar a largura toda", () => {
  const { island } = layout.geometry;
  const bar = (m: number) => layout.spines.find((s) => s.module === m)!.rect;
  const cells = (m: number) => layout.cells.filter((c) => c.module === m);

  it("bancada de 154 px, centrada no mapa", () => {
    expect(island.w).toBe(154);
    expect(island.x).toBe((layout.geometry.map.w - island.w) / 2);
    expect(island.y).toBe((layout.geometry.map.h - island.h) / 2);
  });

  it("barras dos módulos 1 e 5 horizontais, de 22 px e com a largura toda", () => {
    for (const m of [1, 5]) {
      expect(bar(m).w).toBe(island.w);
      expect(bar(m).h).toBe(22);
    }
  });

  it("módulo 1: retângulos em cima e barra em baixo; módulo 5: barra em cima e retângulos em baixo", () => {
    for (const c of cells(1)) expect(c.rect.y + c.rect.h).toBeLessThanOrEqual(bar(1).y);
    for (const c of cells(5)) expect(c.rect.y).toBeGreaterThanOrEqual(bar(5).y + bar(5).h);
  });

  it("entre a barra 1 e a 2, e entre a 5 e a 4, há o mesmo espaço branco de 4 px que entre os outros módulos", () => {
    const gap = layout.geometry.gap_modules;
    expect(gap).toBe(4);
    expect(bar(2).y - (bar(1).y + bar(1).h)).toBe(gap);
    expect(bar(5).y - (bar(4).y + bar(4).h)).toBe(gap);
    // as barras verticais estão centradas por baixo/por cima das horizontais (formam um T)
    for (const [horizontal, vertical] of [[1, 2], [5, 4]]) {
      const h = bar(horizontal);
      const v = bar(vertical);
      expect(v.x).toBeGreaterThanOrEqual(h.x);
      expect(v.x + v.w).toBeLessThanOrEqual(h.x + h.w);
    }
  });

  it("os módulos 2 a 4 mantêm as faces e as barras com 88 px", () => {
    for (const f of layout.faces.filter((f) => f.module >= 2 && f.module <= 4)) expect(f.rect.h).toBe(88);
    for (const m of [2, 3, 4]) expect(bar(m).h).toBe(88);
  });

  it("os retângulos das pontas ocupam a largura toda (2 colunas de 76 px, 3 de 50 px) com os mesmos 4 e 6 area_ids", () => {
    expect(cells(1)).toHaveLength(4);
    expect(cells(5)).toHaveLength(6);
    expect(new Set(cells(1).map((c) => c.rect.w))).toEqual(new Set([76]));
    expect(new Set(cells(5).map((c) => c.rect.w))).toEqual(new Set([50]));
    for (const m of [1, 5]) {
      expect(Math.min(...cells(m).map((c) => c.rect.x))).toBe(0);
      expect(Math.max(...cells(m).map((c) => c.rect.x + c.rect.w))).toBe(island.w);
    }
  });
});

