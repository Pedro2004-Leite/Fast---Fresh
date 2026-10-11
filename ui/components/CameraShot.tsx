"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { Shot } from "@/lib/cameraShots";
import { HEADER_H, STRIP_H } from "@/lib/mapLayout";
import type { AlertKind, Severity, Warning } from "@/lib/types";
import { SEVERITY_BG, SEVERITY_INK } from "./SeverityBadge";

const KIND_TAG: Record<AlertKind, string> = {
  wrong: "PRODUTO ERRADO",
  empty: "VAZIO",
  complaint: "RECLAMAÇÃO",
  blind: "SEM IMAGEM",
};

const SEVERITY_STROKE: Record<Severity, string> = {
  critical: "var(--color-sev-critical)",
  high: "var(--color-sev-high)",
  medium: "var(--color-sev-medium)",
};

/** A foto com o retângulo do planograma a piscar na zona do problema e a etiqueta do tipo de aviso. */
function Photo({ shot, warning, sizes }: { shot: Shot; warning: Warning; sizes: string }) {
  const { severity, kind } = warning;
  const camera = warning.area_id.split("_")[0];
  return (
    <div className="relative size-full overflow-hidden">
      <Image
        src={shot.image}
        alt={`Foto da câmara ${camera}: ${warning.name}`}
        width={480}
        height={600}
        sizes={sizes}
        unoptimized
        className="size-full object-cover"
      />
      {shot.rect ? (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" className="absolute inset-0 size-full">
          <rect
            x={shot.rect.x}
            y={shot.rect.y}
            width={shot.rect.w}
            height={shot.rect.h}
            fill="none"
            strokeWidth={3}
            strokeDasharray="5 3"
            vectorEffect="non-scaling-stroke"
            className="motion-safe:animate-blink"
            style={{ stroke: SEVERITY_STROKE[severity] }}
          />
        </svg>
      ) : null}
      <span
        className={`absolute top-1.5 left-1.5 rounded-full px-2 py-0.5 text-mono-id font-extrabold tracking-wide ${SEVERITY_BG[severity]} ${SEVERITY_INK[severity]}`}
      >
        {KIND_TAG[kind]}
      </span>
    </div>
  );
}

/**
 * A foto da câmara do aviso, à direita do mapa. Tocar amplia-a. Só o "produto errado" tem texto por baixo:
 * o que o planograma pede nesse lugar.
 */
export function CameraShot({ shot, warning }: { shot: Shot; warning: Warning }) {
  const [big, setBig] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!big) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setBig(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [big]);

  return (
    <>
      <div className="absolute right-2 z-10 flex flex-col gap-2 motion-safe:animate-task-in" style={{ left: 190, top: HEADER_H + STRIP_H }}>
        <button
          type="button"
          onClick={() => setBig(true)}
          aria-label="Ampliar a foto da câmara"
          className="m-0 aspect-[4/5] w-full cursor-zoom-in overflow-hidden rounded-card border-0 bg-sheet p-0"
        >
          <Photo shot={shot} warning={warning} sizes="192px" />
        </button>
        {warning.kind === "wrong" && shot.expected ? (
          <p className="m-0 px-1">
            <span className="block text-mono-id font-extrabold tracking-wide text-ink-secondary uppercase">Devia estar aqui</span>
            <b className="text-product font-extrabold">{shot.expected}</b>
          </p>
        ) : null}
      </div>

      {big ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Foto da câmara"
          onClick={() => setBig(false)}
          className="absolute inset-0 z-50 flex items-center justify-center bg-ink/85 p-gutter"
        >
          <div className="aspect-[4/5] max-h-full w-full max-w-[360px] overflow-hidden rounded-card">
            <Photo shot={shot} warning={warning} sizes="360px" />
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={() => setBig(false)}
            aria-label="Fechar a foto"
            className="absolute top-2 right-2 m-0 size-touch cursor-pointer rounded-full border-0 bg-sheet p-0 text-[22px] font-extrabold text-ink"
          >
            ×
          </button>
        </div>
      ) : null}
    </>
  );
}
