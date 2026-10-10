"use client";

import { useEffect, useRef, useState } from "react";

/** A largura e a altura de um elemento, sempre atualizadas. */
export function useElementSize<T extends HTMLElement>(initial = { w: 390, h: 420 }) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState(initial);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setSize((cur) => (cur.w === r.width && cur.h === r.height ? cur : { w: r.width, h: r.height }));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, size] as const;
}
