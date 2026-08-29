import type { ParseDemandResponse } from '../types';

const DEMO_INPUTS: Record<string, ParseDemandResponse> = {
  'customer_marketing': {
    raw_text: '我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。',
    normalized_query: '筛选县域新客 首贷营销 转化概率排名名单',
    intent: 'customer_marketing',
    intent_confidence: 0.94,
    domain: '客户营销',
    business_scenario: '县域新客首贷营销',
    business_stage: '贷前营销',
    customer_segment: ['县域新客'],
    product_type: ['首贷'],
    risk_type: [],
    expected_outputs: ['营销名单', '转化概率', '客户排序'],
    constraints: ['仅限县域范围', '新客定义：无本行历史贷款记录'],
    data_conditions: ['客户画像', '交易流水', '征信数据'],
    tags: ['customer_marketing', 'county_new_customer', 'conversion_prediction', 'response_prediction'],
    tag_names: ['客户营销', '县域新客', '转化预测', '响应率预测'],
    tag_confidence: { 'customer_marketing': 0.91, 'county_new_customer': 0.93, 'conversion_prediction': 0.88, 'response_prediction': 0.85 },
    missing_slots: [],
    need_clarification: false,
    clarification_questions: [],
    structured_filters: {
      customer_type: ['new'],
      region: ['county'],
      product_category: ['first_loan'],
      business_stage: ['pre_loan_marketing'],
    },
    business_to_model_translation: '业务需求"筛选县域新客做首贷营销"对应模型任务类型为"客户响应预测"和"转化概率估算"，属于分类与排序问题。目标变量为"是否响应营销活动"，特征需包含客户基本信息、历史交易行为、县域宏观经济指标。',
    user_confirmable_summary: '需求确认：您需要为**县域新客**群体进行**首贷营销**，期望输出**转化概率排序的营销名单**。系统将识别为"客户营销-贷前营销"场景。',
  },
  'credit_pre_loan': {
    raw_text: '帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。',
    normalized_query: '农户小额贷款 贷前准入风控 欺诈识别 额度建议',
    intent: 'credit_pre_loan_risk_control',
    intent_confidence: 0.96,
    domain: '信贷风控',
    business_scenario: '农户小额贷款贷前准入',
    business_stage: '贷前风控',
    customer_segment: ['农户', '个体农户'],
    product_type: ['小额贷款'],
    risk_type: ['欺诈风险', '信用风险'],
    expected_outputs: ['欺诈评分', '准入结果', '建议额度'],
    constraints: ['贷款金额不超过30万', '农户身份需核实'],
    data_conditions: ['农户基本信息', '农业生产数据', '征信报告', '反欺诈数据'],
    tags: ['credit_risk', 'farmer', 'anti_fraud', 'amount_estimation', 'pre_loan'],
    tag_names: ['信贷风控', '农户', '反欺诈', '额度测算', '贷前'],
    tag_confidence: { 'credit_risk': 0.95, 'farmer': 0.93, 'anti_fraud': 0.90, 'amount_estimation': 0.87, 'pre_loan': 0.92 },
    missing_slots: ['具体贷款金额范围未明确指出'],
    need_clarification: true,
    clarification_questions: [
      {
        question_id: 'q1',
        question_text: '农户小额贷款的单笔金额范围大概是多少？',
        options: ['5万以下', '5-15万', '15-30万'],
      },
      {
        question_id: 'q2',
        question_text: '是否有特定的农业生产类型需要聚焦？（如种植、养殖、农机等）',
        options: ['种植业', '养殖业', '混合经营', '无特定要求'],
      },
    ],
    structured_filters: {
      customer_type: ['farmer', 'individual_farmer'],
      product_category: ['micro_loan'],
      risk_types: ['fraud', 'credit'],
      business_stage: ['pre_loan_risk_control'],
      max_loan_amount: 300000,
    },
    business_to_model_translation: '业务需求"农户小额贷款贷前准入风控"对应模型任务类型为"反欺诈评分""信用评分"和"额度测算"，属于分类与回归问题。反欺诈模型识别虚假申请，准入评分模型评估还款能力，额度测算模型基于还款能力给出建议额度。',
    user_confirmable_summary: '需求确认：您需要为**农户**群体进行**小额贷款贷前准入风控**，期望输出**欺诈评分、准入结果和额度建议**。系统将识别为"信贷风控-贷前风控"场景。',
  },
  'post_loan_early_warning': {
    raw_text: '我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。',
    normalized_query: '对公贷款 贷后逾期预警 预警名单',
    intent: 'post_loan_early_warning',
    intent_confidence: 0.95,
    domain: '信贷风控',
    business_scenario: '对公贷款贷后逾期预警',
    business_stage: '贷后预警',
    customer_segment: ['对公客户', '企业客户'],
    product_type: ['对公贷款'],
    risk_type: ['逾期风险'],
    expected_outputs: ['逾期概率', '风险分层', '预警名单'],
    constraints: ['需对接客户经理工作台', '预警需提前至少30天'],
    data_conditions: ['企业财务报表', '经营流水', '行业数据', '历史还款记录'],
    tags: ['credit_risk', 'corporate', 'default_prediction', 'early_warning', 'post_loan'],
    tag_names: ['信贷风控', '对公客户', '违约预测', '预警监测', '贷后'],
    tag_confidence: { 'credit_risk': 0.94, 'corporate': 0.96, 'default_prediction': 0.92, 'early_warning': 0.88, 'post_loan': 0.90 },
    missing_slots: [],
    need_clarification: false,
    clarification_questions: [],
    structured_filters: {
      customer_type: ['corporate'],
      product_category: ['corporate_loan'],
      risk_types: ['default'],
      business_stage: ['post_loan_early_warning'],
    },
    business_to_model_translation: '业务需求"对公贷款贷后逾期预警"对应模型任务类型为"违约预测"和"风险分层"，属于分类与排序问题。目标变量为"未来是否逾期"，特征需包含企业财务指标、经营流水变化趋势、行业景气度、历史还款行为。',
    user_confirmable_summary: '需求确认：您需要为**对公客户**进行**贷后逾期预警**，期望输出**逾期概率、风险分层和预警名单**。系统将识别为"信贷风控-贷后预警"场景。',
  },
};

export function parseMock(rawText: string): ParseDemandResponse {
  // Try to match known inputs
  const knownKeys = ['customer_marketing', 'credit_pre_loan', 'post_loan_early_warning'];
  for (const key of knownKeys) {
    const demo = DEMO_INPUTS[key];
    if (demo && rawText.includes(demo.raw_text.slice(0, 10))) {
      return { ...demo };
    }
  }

  // Default: return customer_marketing with clarification needed
  return {
    ...DEMO_INPUTS['customer_marketing'],
    raw_text: rawText,
    normalized_query: rawText,
    need_clarification: true,
    clarification_questions: [
      {
        question_id: 'q1',
        question_text: '您主要关注哪个业务领域？',
        options: ['客户营销', '信贷风控', '客户流失预警'],
      },
      {
        question_id: 'q2',
        question_text: '您期望的模型输出形式是？',
        options: ['评分/概率', '名单/排序', '分类标签'],
      },
    ],
  };
}
