import type { ReactNode } from "react";
import { ICON_PATH } from "@/lib/icons";

type Props = {
  name: string;
  store: string;
  refreshing: boolean;
  onRefresh: () => void;
  /** O mapa mostra o nível de stock (em vez dos avisos). Só no ecrã que tem esse modo. */
  levelView?: boolean;
  onToggleLevelView?: () => void;
  /** Algo à direita do nome, antes dos botões (por exemplo "1 de 6"). */
  trailing?: ReactNode;
};

export function Header({ name, store, refreshing, onRefresh, levelView = false, onToggleLevelView, trailing }: Props) {
  return (
    <header className="box-border flex h-header flex-none items-center gap-3 px-gutter">
      <span
        role="img"
        aria-label={name}
        className="box-border flex size-10 flex-none items-center justify-center rounded-full border-2 border-ink bg-map"
      >
        <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
          <path className="fill-ink" d={ICON_PATH.avatarShoulders} />
          <circle className="fill-ink stroke-map" strokeWidth="1.6" cx="12" cy="8" r="4.4" />
        </svg>
      </span>
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-staff leading-[1.1] font-extrabold">{name}</span>
        <span className="truncate text-secondary leading-[1.2] font-semibold text-ink-sub">{store}</span>
      </div>
      {trailing ? <div className="ml-auto flex-none">{trailing}</div> : <div className="ml-auto" />}
      {onToggleLevelView ? (
        <button
          type="button"
          onClick={onToggleLevelView}
          aria-pressed={levelView}
          aria-label="Ver o nível de stock no mapa"
          className={`m-0 flex size-touch flex-none cursor-pointer items-center justify-center rounded-full border-2 p-0 ${
            levelView ? "border-level-active bg-level-active text-white" : "border-ink bg-map text-ink"
          }`}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            className="stroke-current stroke-[2.2]"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d={ICON_PATH.layers} />
          </svg>
        </button>
      ) : null}
      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        aria-label="Atualizar avisos"
        aria-busy={refreshing}
        className="m-0 flex size-touch flex-none cursor-pointer items-center justify-center rounded-full border-0 bg-ink p-0 text-ink-on disabled:cursor-progress"
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          className={`stroke-current stroke-[2.4] ${refreshing ? "motion-safe:animate-spin" : ""}`}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d={ICON_PATH.refresh} />
        </svg>
      </button>
    </header>
  );
}
