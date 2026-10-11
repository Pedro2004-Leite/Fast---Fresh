import { geometry } from "./layout";

export const HEADER_H = 56;
/** A barra de separadores. */
export const NAV_H = 48;
/** A faixa com o contador, acima do mapa (separada dele). */
export const STRIP_H = 48;
/** O mapa nunca cresce mais do que isto, mesmo que haja espaço. */
export const MAX_SCALE = 1.7;

/**
 * O tamanho do mapa no ecrã "só mapa". O mapa enche a zona livre entre a faixa e o fundo; quando se abre uma
 * tarefa, ela ocupa o sítio da barra de separadores (de baixo) e o mapa encolhe para o que sobra.
 */
export function mapLayout(frameHeight: number, cardHeight: number, open: boolean, frameWidth = geometry.map.w, beside = false) {
  const bottomOffset = open ? cardHeight : NAV_H;
  const areaH = Math.max(0, frameHeight - HEADER_H - STRIP_H - bottomOffset);
  // Com a foto da câmara ao lado, a bancada encosta à esquerda, numa coluna estreita.
  const colW = beside ? BESIDE_MAP_W : frameWidth;
  const fit = beside ? (colW - 2 * BESIDE_MARGIN) / geometry.island.w : Infinity;
  const scale = Math.min(areaH / geometry.map.h, MAX_SCALE, fit);
  const top = Math.max(0, (areaH - geometry.map.h * scale) / 2);
  const left = beside ? BESIDE_MARGIN - geometry.island.x * scale : (frameWidth - geometry.map.w * scale) / 2;
  return { bottomOffset, areaH, scale, top, left, width: colW };
}

/** A largura da coluna do mapa quando a foto da câmara aparece ao lado, e a folga da bancada ao bordo. */
export const BESIDE_MAP_W = 182;
export const BESIDE_MARGIN = 3;

/** Com o mapa ampliado, a bolinha "Tu" encosta ao canto visível em vez de sair do ecrã. */
export function userX(scale: number): number {
  const left = geometry.map.w / 2 - geometry.map.w / 2 / scale;
  return Math.max(geometry.user_position.x, left + 20);
}

export type MapView = { scale: number; tx: number; ty: number };

/** Os pontos do desenho da planta (390 x 480) a enquadrar. */
type P = { x: number; y: number };

/** O que se vê, no mínimo, do desenho (px): as tarefas curtas não aproximam mais do que as longas. */
const MIN_VIEW_W = 322;
const MIN_VIEW_H = 318;

/**
 * O mapa aproximado à zona do caminho (do "Tu" ao aviso), centrada na área disponível.
 * O "Tu", o caminho e o aviso ficam sempre à vista. Para não se perder o sentido de orientação, vê-se sempre
 * pelo menos 322 x 318 px do desenho (várias bancadas e as barras com número), mesmo que o caminho seja curto,
 * e a janela não sai do desenho (não mostra branco à volta). A escala fica entre 0,85 e 1,6.
 */
export function routeZoom(route: P[], target: P, areaW: number, areaH: number): MapView {
  const PAD = 26;
  const pts = [...route, { x: target.x - 30, y: target.y - 20 }, { x: target.x + 30, y: target.y + 20 }];
  const x0 = Math.min(...pts.map((p) => p.x)) - PAD;
  const x1 = Math.max(...pts.map((p) => p.x)) + PAD;
  const y0 = Math.min(...pts.map((p) => p.y)) - PAD;
  const y1 = Math.max(...pts.map((p) => p.y)) + PAD;
  const viewW = Math.max(x1 - x0, MIN_VIEW_W);
  const viewH = Math.max(y1 - y0, MIN_VIEW_H);
  const scale = Math.max(0.85, Math.min(areaW / viewW, areaH / viewH, 1.6));

  // a janela visível, em px do desenho: centrada no caminho e, se possível, dentro do desenho
  const place = (from: number, to: number, win: number, whole: number) => {
    if (win >= whole) return (whole - win) / 2; // cabe tudo: centra o desenho
    const centered = (from + to) / 2 - win / 2;
    const inside = Math.min(Math.max(centered, 0), whole - win);
    return from >= inside && to <= inside + win ? inside : centered;
  };
  const left = place(x0, x1, areaW / scale, geometry.map.w);
  const top = place(y0, y1, areaH / scale, geometry.map.h);
  return { scale, tx: -left * scale, ty: -top * scale };
}

/** A bancada toda, encaixada na área (sem tarefa: "Tudo tratado"). */
export function fitAll(areaW: number, areaH: number): MapView {
  const scale = Math.min(areaW / geometry.map.w, areaH / geometry.map.h, 1.25);
  return { scale, tx: (areaW - geometry.map.w * scale) / 2, ty: (areaH - geometry.map.h * scale) / 2 };
}
