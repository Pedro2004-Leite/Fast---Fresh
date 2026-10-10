import { midpointOf } from "@/lib/route";
import type { Point } from "@/lib/types";

type Props = {
  points: Point[];
  /** A escala do mapa: o letreiro desfaz-a para ter sempre o mesmo tamanho. */
  scale?: number;
  /** Por exemplo "12 m". */
  label: string;
};

/**
 * O caminho a pé até ao aviso, a pontinhos, com o letreiro da distância a meio.
 * Vai por baixo da bancada (o SVG) e do letreiro por cima.
 */
export function RoutePath({ points, label, scale = 1 }: Props) {
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const mid = midpointOf(points);
  return (
    <>
      <svg
        width="390"
        height="480"
        viewBox="0 0 390 480"
        aria-hidden="true"
        className="pointer-events-none absolute top-0 left-0 z-0"
      >
        <path d={d} className="fill-none stroke-map" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
        <path
          d={d}
          className="fill-none stroke-ink"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="0.1 9"
        />
      </svg>
      <span
        className="absolute z-[5] flex h-6 min-w-[52px] items-center justify-center rounded-badge bg-ink px-2 font-mono text-mono-id font-semibold text-white"
        style={{ left: Math.round(mid.x), top: Math.round(mid.y), transform: `translate(-50%, -50%) scale(${1 / scale})` }}
      >
        {label}
      </span>
    </>
  );
}
