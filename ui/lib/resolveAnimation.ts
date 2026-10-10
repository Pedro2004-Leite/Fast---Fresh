/**
 * Como um aviso resolvido sai: a bola da gravidade viaja até ao retângulo no mapa (que depois pulsa)
 * enquanto a linha se fecha. Se o retângulo não se vê (painel aberto), a linha varre para a direita.
 * Com movimento reduzido não há animação.
 */
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function collapse(row: HTMLElement, delay = 0): Promise<void> {
  const height = row.offsetHeight;
  row.style.overflow = "hidden";
  const animation = row.animate(
    [
      { height: `${height}px`, opacity: 1 },
      { height: "0px", opacity: 0 },
    ],
    { duration: 240, delay, easing: "ease", fill: "forwards" },
  );
  return animation.finished.then(() => undefined);
}

async function sweep(row: HTMLElement): Promise<void> {
  const animation = row.animate(
    [
      { transform: "translateX(0)", opacity: 1 },
      { transform: "translateX(105%)", opacity: 0 },
    ],
    { duration: 280, easing: "ease-in", fill: "forwards" },
  );
  await animation.finished;
  await collapse(row);
}

const cellOf = (areaId: string) => document.querySelector<HTMLElement>(`[data-cell="${CSS.escape(areaId)}"]`);

function isShown(cell: HTMLElement): boolean {
  const r = cell.getBoundingClientRect();
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!top && !!top.closest("[data-bench]");
}

/** Esmaece a linha sem lhe mexer na altura (o cartão do mapa desliza para baixo por si). */
function fade(row: HTMLElement): Promise<void> {
  return row.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: "ease", fill: "forwards" }).finished.then(
    () => undefined,
  );
}

async function fly(dot: HTMLElement, cell: HTMLElement, row: HTMLElement, closeRow: boolean): Promise<void> {
  const from = dot.getBoundingClientRect();
  const to = cell.getBoundingClientRect();
  const size = 28;
  const ball = document.createElement("div");
  Object.assign(ball.style, {
    position: "fixed",
    zIndex: "50",
    pointerEvents: "none",
    borderRadius: "50%",
    background: getComputedStyle(dot).backgroundColor,
    width: `${size}px`,
    height: `${size}px`,
    left: `${from.left + from.width / 2 - size / 2}px`,
    top: `${from.top + from.height / 2 - size / 2}px`,
  });
  document.body.appendChild(ball);
  dot.style.visibility = "hidden";
  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  const scale = Math.max(0.3, Math.min(to.width, to.height) / size);
  const flight = ball.animate(
    [
      { transform: "translate(0, 0) scale(1)" },
      { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0.9 },
    ],
    { duration: 520, easing: "cubic-bezier(.4, 0, .2, 1)", fill: "forwards" },
  );
  await Promise.all([flight.finished, closeRow ? collapse(row, 200) : fade(row)]);
  ball.remove();
}

/** Corre a animação de saída. Resolve quando a linha já se fechou. */
export async function playResolveAnimation(
  row: HTMLElement | null,
  areaId: string,
  options: { collapse?: boolean } = {},
): Promise<void> {
  if (!row || reduced()) return;
  const dot = row.querySelector<HTMLElement>("[data-severity-dot]");
  const cell = cellOf(areaId);
  const closeRow = options.collapse ?? true;
  if (dot && cell && isShown(cell)) await fly(dot, cell, row, closeRow);
  else if (closeRow) await sweep(row);
  else await fade(row);
}

/** Um pulso à volta do retângulo que ficou tratado. */
export function pulseCell(areaId: string): void {
  const cell = cellOf(areaId);
  if (!cell || reduced()) return;
  cell.animate(
    [{ boxShadow: "0 0 0 0 rgba(39, 40, 42, .45)" }, { boxShadow: "0 0 0 8px rgba(39, 40, 42, 0)" }],
    { duration: 600, easing: "ease-out" },
  );
}
