type Option<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
};

/** Controlo segmentado (por exemplo "Gravidade | Mais perto"). */
export function SegmentedControl<T extends string>({ options, value, onChange, ariaLabel }: Props<T>) {
  return (
    <div role="group" aria-label={ariaLabel} className="flex gap-1 rounded-segmented bg-track-segmented p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`m-0 h-touch flex-1 cursor-pointer rounded-segmented-item border-0 font-[inherit] text-button font-extrabold ${
            value === o.value ? "bg-ink text-ink-on" : "bg-transparent text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
