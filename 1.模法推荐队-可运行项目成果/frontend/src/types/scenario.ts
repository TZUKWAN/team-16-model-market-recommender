/** Types for business scenario library and script generation. */

export interface TypicalScripts {
  marketing: string;
  risk_notice: string;
  outreach: string;
}

export interface BusinessScenario {
  scenario_id: string;
  name: string;
  domain: string;
  business_stage: string;
  description: string;
  typical_scripts: TypicalScripts;
  applicable_models: string[];
  data_requirements: string[];
  compliance_notes: string;
  keywords: string[];
}

export interface ScenarioMatchItem {
  scenario: BusinessScenario;
  match_score: number;
  matched_keywords: string[];
  match_reason: string;
}

export interface ScenarioMatchResponse {
  matches: ScenarioMatchItem[];
  total_scenarios: number;
}

export interface ScenarioMatchRequest {
  parse_result: Record<string, unknown>;
  top_k: number;
}

export interface GeneratedScript {
  scenario_id: string;
  scenario_name: string;
  script_type: string;
  content: string;
  disclaimer: string;
  llm_used: boolean;
  basis: string;
}

export interface ScriptGenerateResponse {
  script: GeneratedScript;
}

export interface ScriptGenerateRequest {
  scenario_id: string;
  parse_result: Record<string, unknown>;
  script_type: string;
}
