import { levelBackground, LEVEL_TEXT, type AreaLevel } from "@/lib/levels";

const ITEMS: { level: AreaLevel; text: string }[] = [
  { level: "full", text: LEVEL_TEXT.full },
  { level: "half", text: LEVEL_TEXT.half },
  { level: "empty", text: LEVEL_TEXT.empty },
  { level: null, text: LEVEL_TEXT.none },
];

/** Legenda do modo Nível, na margem esquerda do mapa. */
export function LevelLegend() {
  return (
    <ul
      aria-label="Legenda do nível de stock"
      className="absolute top-[34px] left-5 m-0 flex list-none flex-col gap-1.5 p-0 font-sans text-mono-id font-bold"
    >
      {ITEMS.map((item) => (
        <li key={item.text} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-3.5 w-[22px] rounded-cell"
            style={{ background: levelBackground(item.level) }}
          />
          {item.text}
        </li>
      ))}
    </ul>
  );
}
