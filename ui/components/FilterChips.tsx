import { SEVERITY_LABEL } from "@/lib/severity";
import type { Severity } from "@/lib/types";
import { SEVERITY_BG } from "./SeverityBadge";

export type Filter = "all" | Severity;

type Props = {
  value: Filter;
  counts: Record<Filter, number>;
  onChange: (filter: Filter) => void;
};

const ORDER: Filter[] = ["all", "critical", "high", "medium"];

export function FilterChips({ value, counts, onChange }: Props) {
  return (
    <div className="grid flex-none grid-cols-4 gap-2">
      {ORDER.map((key) => {
        const active = value === key;
        const label = key === "all" ? "Todos" : SEVERITY_LABEL[key].label;
        const dot = key === "all" ? "bg-dot" : SEVERITY_BG[key];
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            aria-pressed={active}
            className={`m-0 flex h-chip cursor-pointer flex-col items-start justify-center gap-[3px] rounded-chip border-0 px-2.5 py-1.5 text-left font-[inherit] ${
              active ? "bg-ink text-ink-on" : "bg-chip text-ink"
            }`}
          >
            <span className="flex items-center gap-1.5">
              <span className={`size-[22px] rounded-full ${dot}`} aria-hidden="true" />
              <span className="font-mono text-count leading-none font-semibold">{counts[key]}</span>
            </span>
            <span className="text-secondary font-bold">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
