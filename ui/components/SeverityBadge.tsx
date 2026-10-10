import type { Severity } from "@/lib/types";

/** Classes completas (o Tailwind só gera o que vê escrito). */
export const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
};

export const SEVERITY_INK: Record<Severity, string> = {
  critical: "text-sev-critical-ink",
  high: "text-sev-high-ink",
  medium: "text-sev-medium-ink",
};

/** Distintivo de gravidade: uma bola com a cor da gravidade, sem símbolo. A palavra da gravidade vai no texto da linha. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="flex size-touch flex-none items-center justify-center" aria-hidden="true">
      <span data-severity-dot className={`size-7 rounded-full ${SEVERITY_BG[severity]}`} />
    </span>
  );
}
