"use client";

import { useEffect, useRef, useState } from "react";

/** A altura de um elemento, sempre atualizada (o ecrã do telemóvel muda quando a barra do Safari se mexe). */
export function useElementHeight<T extends HTMLElement>(initial = 844) {
  const ref = useRef<T>(null);
  const [height, setHeight] = useState(initial);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setHeight(el.getBoundingClientRect().height));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, height] as const;
}
