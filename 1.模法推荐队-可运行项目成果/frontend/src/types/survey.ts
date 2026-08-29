export type SurveyRole =
  | 'business'
  | 'risk'
  | 'product'
  | 'operations'
  | 'compliance'
  | 'technology';

export type SurveyScenario =
  | 'credit_risk'
  | 'customer_marketing'
  | 'operation_management';

export interface SurveyCampaignInfo {
  campaign_id: string;
  name: string;
  status: 'active' | 'closed';
  created_at: string;
  samples_per_respondent: number;
  minimum_respondents: number;
  required_roles: SurveyRole[];
  required_scenarios: SurveyScenario[];
  invitation_count: number;
  questionnaire_version: string;
}

export interface SurveyQuestionDefinition {
  question_id: `q${1 | 2 | 3 | 4 | 5 | 6 | 7 | 8}`;
  text: string;
  dimension: string;
}

export interface SurveyDefinitionResponse {
  campaign: SurveyCampaignInfo;
  questions: SurveyQuestionDefinition[];
  scale_min: number;
  scale_max: number;
  understandable_threshold: number;
}

export interface SurveyAnswers {
  q1: number;
  q2: number;
  q3: number;
  q4: number;
  q5: number;
  q6: number;
  q7: number;
  q8: number;
}

export interface SurveyOpenFeedback {
  most_helpful?: string;
  still_unclear?: string;
  main_risk?: string;
  desired_improvements?: string;
}

export interface SurveySubmissionRequest {
  campaign_id: string;
  invitation_token: string;
  sample_id: string;
  scenario_id: SurveyScenario;
  department: SurveyRole;
  role: SurveyRole;
  answers: SurveyAnswers;
  open_feedback: SurveyOpenFeedback;
  consent_confirmed: boolean;
}

export interface SurveySubmissionResponse {
  response_id: string;
  accepted_samples: number;
  required_samples: number;
  respondent_complete: boolean;
  formal_evidence_verified: false;
}

export interface SurveyAccess {
  campaignId: string;
  invitationToken: string;
}
