/** 需求解析响应 */
export interface ParseDemandResponse {
  raw_text: string;
  normalized_query: string;
  intent: string;
  intent_confidence: number;
  domain: string;
  business_scenario: string;
  business_stage: string;
  customer_segment: string[];
  product_type: string[];
  risk_type: string[];
  expected_outputs: string[];
  constraints: string[];
  data_conditions: string[];
  tags: string[];
  tag_names: string[];
  tag_confidence: Record<string, number>;
  missing_slots: string[];
  need_clarification: boolean;
  clarification_questions: ClarificationQuestion[];
  structured_filters: Record<string, any>;
  business_to_model_translation: string;
  user_confirmable_summary: string;
  parse_source?: 'rule' | 'llm' | 'hybrid_fallback' | 'error_fallback';
  llm_enabled?: boolean;
  llm_trace_id?: string | null;
  /** 多轮澄清会话 id（后端创建并返回，后续轮次需回传） */
  session_id?: string;
  /** 当前澄清轮次（后端权威，1-based） */
  clarification_round?: number;
  /** 会话是否已收敛，无需再追问 */
  conversation_converged?: boolean;
}

export interface ClarificationQuestion {
  question_id: string;
  question_text: string;
  options?: string[];
  user_answer?: string;
}
