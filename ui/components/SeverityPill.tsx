import { SEVERITY_LABEL } from "@/lib/severity";
import type { Severity } from "@/lib/types";
import { SEVERITY_BG, SEVERITY_INK } from "./SeverityBadge";

/** A gravidade em palavra, numa pílula com a cor da gravidade (sem símbolo). */
export function SeverityPill({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex h-6 items-center rounded-badge px-2.5 font-sans text-mono-id font-extrabold tracking-[0.06em] ${SEVERITY_BG[severity]} ${SEVERITY_INK[severity]}`}
    >
      {SEVERITY_LABEL[severity].word}
    </span>
  );
}
