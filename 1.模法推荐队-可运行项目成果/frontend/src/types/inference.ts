export interface ModelInvokeRequest {
  input_data?: Record<string, unknown>;
  async_mode?: boolean;
  request_context?: Record<string, unknown>;
}

export interface ModelInvokeResponse {
  model_id: string;
  task_id: string;
  status: string;
  demo_data: boolean;
  submitted_at: string;
  message: string;
  result: ModelResultPayload;
}

export interface ModelResultResponse {
  task_id: string;
  status: string;
  demo_data: boolean;
  result: ModelResultPayload;
}

export interface ModelResultPayload {
  model_id?: string;
  demo_data?: boolean;
  result_type?: string;
  input_echo_keys?: string[];
  desensitized_notice?: string;
  compliance_notice?: string;
  usage_boundary?: string;
  compliance?: {
    result_type?: string;
    sensitivity_level?: string;
    usage_boundary?: string;
    allowed_usage?: string[];
    prohibited_usage?: string[];
    default_desensitized?: boolean;
    sensitive_fields_masked?: string[];
    field_registry_loaded?: boolean;
  };
  rows?: Record<string, unknown>[];
}
