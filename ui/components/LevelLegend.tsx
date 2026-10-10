import { levelBackground, LEVEL_TEXT, type AreaLevel } from "@/lib/levels";

const ITEMS: { level: AreaLevel; text: string }[] = [
  { level: "full", text: LEVEL_TEXT.full },
  { level: "half", text: LEVEL_TEXT.half },
  { level: "empty", text: LEVEL_TEXT.empty },
  { level: null, text: LEVEL_TEXT.none },
];

/** Legenda do modo Nível, em linha (na faixa por cima do mapa). */
export function LevelLegend() {
  return (
    <ul aria-label="Legenda do nível de stock" className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0 font-sans text-mono-id font-bold">
      {ITEMS.map((item) => (
        <li key={item.text} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-3.5 w-[18px] rounded-cell" style={{ background: levelBackground(item.level) }} />
          {item.text}
        </li>
      ))}
    </ul>
  );
}
