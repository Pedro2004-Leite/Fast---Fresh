import { describe, expect, it } from "vitest";
import { applyRefresh, getSampleEvents, INCOMING_BATCHES, resolveReadings } from "../events";
import { cellAtPoint, cellOf, layout } from "../layout";
import { levelsOf, levelBackground } from "../levels";
import { buildWarnings } from "../warnings";

describe("atualizar", () => {
  const base = getSampleEvents();

  it("as leituras novas substituem as antigas da mesma área; as outras envelhecem", () => {
    const r = applyRefresh(base, INCOMING_BATCHES[0], 2);
    expect(r.addedIds).toEqual(["6376_2", "6462_3"]);
    expect(r.events).toHaveLength(56);
    expect(r.events.find((e) => e.area_id === "6376_2")).toMatchObject({ stock_level: "empty", minutes_ago: 1 });
    const before = base.find((e) => e.area_id === "6373_1")!.minutes_ago;
    expect(r.events.find((e) => e.area_id === "6373_1")!.minutes_ago).toBe(before + 2);
  });

  it("sem leituras novas, só envelhece", () => {
    const r = applyRefresh(base, [], 2);
    expect(r.addedIds).toEqual([]);
    expect(r.events.map((e) => e.stock_level)).toEqual(base.map((e) => e.stock_level));
  });

  it("não altera a lista original", () => {
    const copy = JSON.stringify(base);
    applyRefresh(base, INCOMING_BATCHES[0]);
    expect(JSON.stringify(base)).toBe(copy);
  });

  it("as leituras de exemplo existem na bancada e todas dão aviso", () => {
    for (const batch of INCOMING_BATCHES) {
      for (const e of batch) expect(cellOf(e.area_id), e.area_id).toBeDefined();
      expect(buildWarnings(batch)).toHaveLength(batch.length);
    }
  });
});

describe("resolver", () => {
  const base = getSampleEvents();

  it("repor deixa o retângulo cheio e sem aviso", () => {
    const events = resolveReadings(base, ["6468_5"]);
    expect(events.find((e) => e.area_id === "6468_5")).toMatchObject({ stock_level: "full", planogram_compliant: true, minutes_ago: 0 });
    expect(buildWarnings(events).some((w) => w.areaIds.includes("6468_5"))).toBe(false);
  });

  it("arrumar um produto errado fica conforme e mantém o stock", () => {
    const wrong = base.find((e) => e.area_id === "6371_2")!;
    const events = resolveReadings(base, ["6371_2"]);
    const after = events.find((e) => e.area_id === "6371_2")!;
    expect(after.planogram_compliant).toBe(true);
    expect(after.stock_level).toBe(wrong.stock_level);
  });

  it("uma câmara sem imagem resolve-se de uma vez, para os 5 retângulos", () => {
    const ids = layout.cells.filter((c) => c.camera_id === "6383").map((c) => c.area_id);
    const events = resolveReadings(base, ids);
    expect(events.filter((e) => ids.includes(e.area_id) && e.minutes_ago === 0)).toHaveLength(5);
    expect(buildWarnings(events).some((w) => w.kind === "blind")).toBe(false);
  });
});

describe("nível de stock", () => {
  it("o nível de cada retângulo vem da leitura", () => {
    const levels = levelsOf(getSampleEvents());
    expect(Object.keys(levels)).toHaveLength(56);
    expect(levels["6468_5"].level).toBe("empty");
    expect(levels["6383_1"]).toEqual({ level: null, minutesAgo: 41 });
  });

  it("o enchimento: cheio 100%, metade 50%, vazio 0%, sem leitura às riscas", () => {
    expect(levelBackground("full")).toContain("0 100%");
    expect(levelBackground("half")).toContain("0 50%");
    expect(levelBackground("empty")).toContain("0 0%");
    expect(levelBackground(null)).toContain("repeating-linear-gradient");
  });

  it("o toque escolhe o retângulo que contém o ponto, ou o mais próximo no espaço entre retângulos", () => {
    const c = layout.cells.find((x) => x.area_id === "6373_1")!;
    const mid = { x: c.rect.x + c.rect.w / 2, y: c.rect.y + c.rect.h / 2 };
    expect(cellAtPoint(mid.x, mid.y)?.area_id).toBe("6373_1");
    expect(cellAtPoint(c.rect.x + c.rect.w + 1, mid.y)).toBeDefined();
    expect(cellAtPoint(-200, -200)).toBeUndefined();
  });
});

describe("caminho até ao aviso", () => {
  it("o letreiro fica a meio do caminho, em px do mapa", async () => {
    const { midpointOf, pathLength } = await import("../route");
    const pts = [
      { x: 60, y: 240 },
      { x: 60, y: 460 },
      { x: 195, y: 460 },
    ];
    const mid = midpointOf(pts);
    // metade de 220 + 135 = 177,5 px: ainda no primeiro troço (220 px)
    expect(pathLength(pts)).toBe(355);
    expect(mid).toEqual({ x: 60, y: 240 + 177.5 });
    expect(midpointOf([{ x: 1, y: 1 }])).toEqual({ x: 1, y: 1 });
  });
});

describe("o mapa sozinho", () => {
  it("fechado, o mapa enche a zona livre; aberto, encolhe para o que sobra acima da tarefa", async () => {
    const { mapLayout, MAX_SCALE, userX } = await import("../mapLayout");
    const closed = mapLayout(844, 176, false);
    expect(closed.bottomOffset).toBe(48);
    expect(closed.areaH).toBe(844 - 56 - 48 - 48);
    expect(closed.scale).toBeCloseTo(closed.areaH / 480, 5);
    const open = mapLayout(844, 176, true);
    expect(open.bottomOffset).toBe(176);
    expect(open.scale).toBeLessThan(closed.scale);
    const claimed = mapLayout(844, 252, true);
    expect(claimed.scale).toBeLessThan(open.scale); // "Vou eu" faz a tarefa crescer: o mapa encolhe mais
    // nunca passa do máximo, mesmo com muito espaço
    expect(mapLayout(3000, 176, false).scale).toBe(MAX_SCALE);
    // "Tu" fica à vista com o mapa ampliado
    expect(userX(1)).toBe(60);
    expect(userX(1.5)).toBeGreaterThan(60);
  });
});

describe("o mapa aproximado à zona do caminho", () => {
  it("o Tu, o caminho e o aviso ficam dentro da área, com escala entre 0,85 e 1,6", async () => {
    const { routeZoom } = await import("../mapLayout");
    const { routeOf } = await import("../route");
    const { buildWarnings } = await import("../warnings");
    const ws = buildWarnings(getSampleEvents());
    expect(ws.length).toBeGreaterThan(5);
    for (const w of ws) {
      const route = routeOf(w.face, w.center);
      for (const [areaW, areaH] of [[390, 388], [390, 298], [390, 568], [358, 300]] as const) {
        const v = routeZoom(route, w.center, areaW, areaH);
        expect(v.scale).toBeGreaterThanOrEqual(0.85);
        expect(v.scale).toBeLessThanOrEqual(1.6);
        // sempre que a escala não foi forçada ao mínimo, tudo cabe na área
        const natural = v.scale > 0.85;
        if (natural) {
          for (const p of [...route, w.center]) {
            const x = p.x * v.scale + v.tx;
            const y = p.y * v.scale + v.ty;
            expect(x, `${w.area_id} x`).toBeGreaterThanOrEqual(-0.5);
            expect(x, `${w.area_id} x`).toBeLessThanOrEqual(areaW + 0.5);
            expect(y, `${w.area_id} y`).toBeGreaterThanOrEqual(-0.5);
            expect(y, `${w.area_id} y`).toBeLessThanOrEqual(areaH + 0.5);
          }
        }
      }
    }
  });

  it("sem tarefa, a bancada toda cabe na área", async () => {
    const { fitAll } = await import("../mapLayout");
    const v = fitAll(390, 400);
    expect(v.scale).toBeLessThanOrEqual(1.25);
    expect(480 * v.scale).toBeLessThanOrEqual(400.001);
  });
});

describe("o zoom não aproxima demais", () => {
  it("todas as tarefas veem pelo menos 322 px de largura do desenho", async () => {
    const { routeZoom } = await import("../mapLayout");
    const { routeOf } = await import("../route");
    const { buildWarnings } = await import("../warnings");
    const ws = buildWarnings(getSampleEvents());
    for (const w of ws) {
      const route = routeOf(w.face, w.center);
      for (const [areaW, areaH] of [[390, 385], [390, 565], [358, 300]] as const) {
        const v = routeZoom(route, w.center, areaW, areaH);
        // as tarefas curtas deixaram de chegar a 1,6x: veem tanto como as longas
        expect(areaW / v.scale, `${w.area_id} largura visível`).toBeGreaterThanOrEqual(areaW === 390 ? 321.5 : 0);
      }
    }
    // o caso mais curto (Kiwi, 4 m) já não chega ao máximo
    const kiwi = ws.find((w) => w.area_id === "6376_2");
    if (kiwi) expect(routeZoom(routeOf(kiwi.face, kiwi.center), kiwi.center, 390, 385).scale).toBeLessThan(1.3);
  });
});
