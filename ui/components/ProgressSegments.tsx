type Props = {
  total: number;
  /** Quantas tarefas já estão resolvidas. */
  done: number;
  /** Há uma tarefa em curso (a seguinte às resolvidas). */
  hasCurrent: boolean;
  label: string;
};

/** Uma barra por tarefa: as resolvidas escuras, a atual a meio, as seguintes claras. */
export function ProgressSegments({ total, done, hasCurrent, label }: Props) {
  return (
    <div role="img" aria-label={`${label} tarefas`} className="flex flex-none gap-1 px-gutter pb-2">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={`h-1.5 flex-1 rounded-[3px] ${
            i < done ? "bg-ink" : i === done && hasCurrent ? "bg-ink/55" : "bg-ink/18"
          }`}
        />
      ))}
    </div>
  );
}
