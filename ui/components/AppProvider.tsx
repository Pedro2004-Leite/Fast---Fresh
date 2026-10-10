"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { useEvents, type UseEvents } from "@/lib/useEvents";
import { useResolveFlow } from "@/lib/useResolveFlow";
import { BottomNav } from "./BottomNav";

type App = UseEvents & {
  /** Assumir e resolver: partilhado por todas as vistas. */
  flow: ReturnType<typeof useResolveFlow>;
  /** Quantas tarefas já foram resolvidas (para o progresso do ecrã C). */
  done: number;
  /** Recomeçar a demonstração: os dados voltam ao início. */
  restart: () => void;
  /** O ecrã do mapa esconde a barra de separadores quando abre uma tarefa no sítio dela. */
  setNavHidden: Dispatch<SetStateAction<boolean>>;
  /** Abre o Mapa com este aviso selecionado (como se tivesses tocado nele no mapa). */
  showOnMap: (areaId: string) => void;
  /** O aviso que o Mapa ainda tem de selecionar ao abrir. O Mapa limpa-o depois de o usar. */
  pendingSelect: string | null;
  clearPendingSelect: () => void;
};

const AppContext = createContext<App | null>(null);

export function useApp(): App {
  const app = useContext(AppContext);
  if (!app) throw new Error("useApp só se usa dentro do AppProvider");
  return app;
}

/**
 * A moldura da aplicação (390 px) e o estado único que as três vistas (Mapa, Lista e Tarefa) partilham:
 * as leituras, o que está "A tratar", o que se resolveu.
 * Vive no layout, por isso não se perde ao mudar de vista.
 */
export function AppProvider({ children }: { children: ReactNode }) {
  const data = useEvents();
  const [done, setDone] = useState(0);
  const [navHidden, setNavHidden] = useState(false);
  const [pendingSelect, setPendingSelect] = useState<string | null>(null);
  const router = useRouter();
  const showOnMap = useCallback(
    (areaId: string) => {
      setPendingSelect(areaId);
      router.push("/");
    },
    [router],
  );
  const clearPendingSelect = useCallback(() => setPendingSelect(null), []);
  const flow = useResolveFlow(data.resolve, {
    onResolved: () => setDone((d) => d + 1),
  });

  const restart = () => {
    data.reset();
    setDone(0);
  };

  return (
    <AppContext value={{ ...data, flow, done, restart, setNavHidden, showOnMap, pendingSelect, clearPendingSelect }}>
      <div className="relative mx-auto h-dvh w-full max-w-[390px] overflow-hidden bg-ground text-ink">
        <div className="absolute inset-0">{children}</div>
        <BottomNav hidden={navHidden} />
        <p role="status" aria-live="polite" className="sr-only">
          {flow.status}
        </p>
      </div>
    </AppContext>
  );
}
