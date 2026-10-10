import { describe, expect, it } from "vitest";
import { applyRefresh, getSampleEvents, INCOMING_BATCHES, resolveReadings, restoreReadings } from "../events";
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

describe("resolver e desfazer", () => {
  const base = getSampleEvents();

  it("repor deixa o retângulo cheio e sem aviso; desfazer volta ao que era", () => {
    const { events, previous } = resolveReadings(base, ["6468_5"]);
    expect(events.find((e) => e.area_id === "6468_5")).toMatchObject({ stock_level: "full", planogram_compliant: true, minutes_ago: 0 });
    expect(buildWarnings(events).some((w) => w.areaIds.includes("6468_5"))).toBe(false);
    expect(restoreReadings(events, previous)).toEqual(base);
  });

  it("arrumar um produto errado fica conforme e mantém o stock", () => {
    const wrong = base.find((e) => e.area_id === "6371_2")!;
    const { events } = resolveReadings(base, ["6371_2"]);
    const after = events.find((e) => e.area_id === "6371_2")!;
    expect(after.planogram_compliant).toBe(true);
    expect(after.stock_level).toBe(wrong.stock_level);
  });

  it("uma câmara sem imagem resolve-se de uma vez, para os 5 retângulos", () => {
    const ids = layout.cells.filter((c) => c.camera_id === "6383").map((c) => c.area_id);
    const { events, previous } = resolveReadings(base, ids);
    expect(previous).toHaveLength(5);
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
