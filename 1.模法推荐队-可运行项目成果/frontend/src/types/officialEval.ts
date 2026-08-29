// ========== Official Dataset Evaluation Types ==========

/** GET /api/v1/official-evaluation/summary */
export interface OfficialEvalSummary {
  generated_at: string;
  top1_accuracy: number;
  top3_accuracy: number;
  top5_accuracy: number;
  val: {
    total: number;
    top1_hits: number;
    top3_hits: number;
    top5_hits: number;
    top1_rate: number;
    top3_rate: number;
    top5_rate: number;
  };
  test: {
    total: number;
    top1_hits: number;
    top3_hits: number;
    top5_hits: number;
    top1_rate: number;
    top3_rate: number;
    top5_rate: number;
  };
  failure_attribution: {
    val: Record<string, number>;
    test: Record<string, number>;
    total: Record<string, number>;
  };
}

/** GET /api/v1/official-evaluation/results?split=val|test */
export interface OfficialEvalResultItem {
  query_id: string;
  split: string;
  query: string;
  gold_model_ids: string[];
  gold_model_names: string[];
  recommended_top5: string[];
  recommended_models: {
    model_id: string;
    model_name: string;
    score: number;
    matched_keywords: string[];
    source_type: string;
  }[];
  top1_hit: boolean;
  top3_hit: boolean;
  top5_hit: boolean;
  failure_type: string | null;
}

export interface OfficialEvalResults {
  split: string;
  total: number;
  top1_hits: number;
  top3_hits: number;
  top5_hits: number;
  top1_rate: number;
  top3_rate: number;
  top5_rate: number;
  results: OfficialEvalResultItem[];
}

/** GET /api/v1/official-evaluation/failures?split=&failure_type= */
export interface OfficialEvalFailure {
  query_id: string;
  split: string;
  query: string;
  gold_model_ids: string[];
  gold_model_names: string[];
  recommended_top5: string[];
  recommended_models: OfficialEvalResultItem['recommended_models'];
  top1_hit: boolean;
  top3_hit: boolean;
  top5_hit: boolean;
  failure_type: string;
  failure_scope: 'top1_miss' | 'top3_miss' | 'top5_miss';
  reason: string;
  suggested_fix: string;
}

/** GET /api/v1/official-evaluation/dataset */
export interface OfficialDatasetInfo {
  manifest: {
    source: string;
    source_archive: string;
    excel_file: string;
    model_count: number;
    raw_model_rows: number;
    duplicate_model_rows: number;
    query_count: number;
    split_counts: { train: number; test: number; val: number };
    source_type_values: string[];
    generated_at: string;
  };
  model_count: number;
  query_count: number;
  splits: { train: number; test: number; val: number };
}
