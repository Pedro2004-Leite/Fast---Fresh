"use client";

import { useEffect, useState } from "react";

type Props = {
  message: string;
  seconds?: number;
  onUndo: () => void;
  onExpire: () => void;
};

/** Barra "Desfazer" depois de resolver: dura alguns segundos e desaparece sozinha. */
export function UndoBar({ message, seconds = 8, onUndo, onExpire }: Props) {
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    const id = window.setInterval(() => setLeft((n) => n - 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (left <= 0) onExpire();
  }, [left, onExpire]);

  return (
    <div
      role="status"
      className="absolute inset-x-gutter bottom-3 z-30 flex items-center justify-between gap-3 rounded-card bg-ink py-1.5 pr-1.5 pl-4 text-message font-bold text-ink-on shadow-sheet"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onUndo}
        className="m-0 h-touch flex-none cursor-pointer rounded-full border-0 bg-map px-3.5 text-button font-extrabold text-ink"
      >
        Desfazer ({Math.max(left, 0)})
      </button>
    </div>
  );
}
