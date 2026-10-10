export type Severity = "critical" | "high" | "medium";

/** O que a câmara lê num retângulo: os 3 estados do desafio. */
export type StockLevel = "empty" | "half" | "full";

/**
 * A leitura de uma area_id (câmara_nº), no formato do desafio (stock_level + planogram_compliant),
 * com reclamação de cliente opcional.
 */
export type AreaEvent = {
  area_id: string;
  /** vazio, metade ou cheio; null = a câmara não vê (sem leitura). */
  stock_level: StockLevel | null;
  /** O produto que lá está é o do planograma. */
  planogram_compliant: boolean;
  complaint?: string | null;
  /** Há quanto tempo é esta leitura (ou, sem leitura, desde a última imagem). */
  minutes_ago: number;
};

export type Side = "A" | "B" | "end";

export type Rect = { x: number; y: number; w: number; h: number };
export type Point = { x: number; y: number };

export type BenchCell = {
  area_id: string;
  camera_id: string;
  module: number;
  side: Side;
  class_key: string;
  nome_pt: string;
  row: number;
  col: number;
  /** relativo ao canto da ilha */
  rect: Rect;
};

export type BenchFace = {
  module: number;
  side: Side;
  label: string;
  cols: number;
  rows: number;
  rect: Rect;
};

export type BenchSpine = { module: number; rect: Rect };

export type BenchGeometry = {
  map: { w: number; h: number };
  island: Rect;
  gap_cells: number;
  gap_modules: number;
  user_position: Point;
  aisle_b_x: number;
  cross_passage_y: { top: number; bottom: number };
  meters_per_px: number;
};

export type BenchLayout = {
  geometry: BenchGeometry;
  spines: BenchSpine[];
  faces: BenchFace[];
  cells: BenchCell[];
};

/** Porque há aviso. */
export type AlertKind = "wrong" | "empty" | "complaint" | "blind";

/** Um aviso: evento com gravidade, local na bancada e distância a pé. */
export type Warning = {
  event: AreaEvent;
  /** O retângulo principal. Uma câmara sem imagem é um aviso só, para todos os seus retângulos. */
  area_id: string;
  areaIds: string[];
  kind: AlertKind;
  /** O que fazer: Repor, Verificar, Produto errado, Verificar a câmara. */
  task: string;
  name: string;
  face: BenchFace;
  severity: Severity;
  distanceM: number;
  /** centro do retângulo, em px do mapa (390 x 480) */
  center: Point;
};
