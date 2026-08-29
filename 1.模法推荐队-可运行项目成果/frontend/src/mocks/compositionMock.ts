import type { CompositionResponse } from '../types';

function buildCreditPreLoanComposition(): CompositionResponse {
  return {
    composition_id: 'COMP_LOAN_PRE_001',
    composition_name: '农户小额贷款贷前准入组合',
    scenario: '贷前风控',
    total_score: 86.5,
    nodes: [
      {
        step_id: 'STEP_1',
        step_order: 1,
        model_id: 'RC_FRD_001',
        model_name: '农户反欺诈评分模型',
        capability: '欺诈识别',
        input_fields: ['农户身份信息', '设备信息', '关系网络数据', '多头借贷数据'],
        output_fields: ['欺诈评分', '欺诈类型标签', '风险等级'],
      },
      {
        step_id: 'STEP_2',
        step_order: 2,
        model_id: 'RC_SCR_002',
        model_name: '农户准入评分模型',
        capability: '信用评估',
        input_fields: ['农户基本信息', '农业生产数据', '征信报告', '经营流水'],
        output_fields: ['准入评分', '信用等级', '建议额度系数'],
      },
      {
        step_id: 'STEP_3',
        step_order: 3,
        model_id: 'RC_AMT_003',
        model_name: '小额贷款额度测算模型',
        capability: '额度建议',
        input_fields: ['农户收入证明', '资产负债数据', '经营计划', '征信报告'],
        output_fields: ['建议额度', '还款能力评分', '期限建议'],
      },
    ],
    flow_edges: [
      { from_step: 'STEP_1', to_step: 'STEP_2', reason: '欺诈评分结果作为准入评分的风险修正因子' },
      { from_step: 'STEP_2', to_step: 'STEP_3', reason: '准入评分和信用等级作为额度测算的基础输入' },
    ],
    io_compatibility: {
      total_edges: 2,
      passed: 1,
      partial: 1,
      failed: 0,
      compatibility_rate: 0.75,
      'STEP_1->STEP_2': {
        matched: ['农户身份信息', '风险等级'],
        unmatched: [],
        notes: 'STEP_1输出的风险等级可作为STEP_2的风险因子输入',
      },
      'STEP_2->STEP_3': {
        matched: ['信用等级', '还款能力指标'],
        unmatched: ['经营计划（STEP_3额外需求）'],
        notes: 'STEP_3需要补充经营计划数据，需单独采集',
      },
    },
    missing_data: ['农业生产数据（季节因素）'],
    expected_outputs: ['欺诈评分（通过/拒绝）', '准入评分（分数）', '建议额度（金额）', '综合风险评级'],
    business_explanation: '这套组合方案按照"先判断是不是骗子→再看能不能还款→最后算给多少钱"的流程工作。第一步排除欺诈风险，第二步评估农户的还款能力和意愿，第三步根据评估结果给出适当的贷款额度建议。三步环环相扣，确保贷前风控既严格又高效。',
    technical_explanation: '组合采用串行流水线架构：Step1 反欺诈模型（XGBoost+关系网络图算法）输出欺诈评分；Step2 准入评分模型（LightGBM）将Step1的风险等级作为特征输入，结合农户特征输出信用评分；Step3 额度测算模型（回归模型）基于评分结果和经营数据输出额度建议。各模型通过标准化API接口通信，支持独立更新和A/B测试。',
    management_explanation: '该组合方案整合了反欺诈、准入评分和额度测算三大核心能力，覆盖贷前准入全流程。相比单模型方案，组合方案的风险控制能力提升约40%，同时保持了流程效率——预计全流程处理时间不超过2分钟。建议优先部署反欺诈模型，再逐步上线评分和额度模型。',
    usage_guide: [
      { step: 'Step 1: 部署反欺诈模型', description: '对接申请渠道，完成设备指纹采集和反欺诈接口联调', estimated_time: '2周', data_preparation: '历史欺诈样本标注、设备指纹SDK集成' },
      { step: 'Step 2: 部署准入评分模型', description: '接入征信和农业生产数据，完成评分接口对接', estimated_time: '3周', data_preparation: '农户样本标注、征信数据源接入' },
      { step: 'Step 3: 部署额度测算模型', description: '完成额度测算策略配置，与核心系统联调', estimated_time: '2周', data_preparation: '额度策略参数、还款能力数据采集' },
      { step: '整体联调上线', description: '全流程串联测试，A/B对比实验，逐步放量', estimated_time: '2周', data_preparation: '全流程测试用例、验收标准' },
    ],
  };
}

function buildPostLoanWarningComposition(): CompositionResponse {
  return {
    composition_id: 'COMP_PLW_001',
    composition_name: '对公贷款贷后预警组合',
    scenario: '贷后预警',
    total_score: 85.2,
    nodes: [
      {
        step_id: 'STEP_1',
        step_order: 1,
        model_id: 'RC_PLW_001',
        model_name: '对公贷款逾期预测模型',
        capability: '逾期概率预测',
        input_fields: ['企业财务报表', '经营流水', '行业数据', '历史还款记录'],
        output_fields: ['逾期概率', '风险评分', '预警等级', '预警时间窗口'],
      },
      {
        step_id: 'STEP_2',
        step_order: 2,
        model_id: 'RC_PLW_002',
        model_name: '企业风险分层模型',
        capability: '风险分层',
        input_fields: ['企业财务数据', '行业分类', '历史违约数据'],
        output_fields: ['风险等级', '风险因子分解', '行业排名'],
      },
      {
        step_id: 'STEP_3',
        step_order: 3,
        model_id: 'RC_PLW_005',
        model_name: '预警名单生成模型',
        capability: '名单输出',
        input_fields: ['风险评分', '客户经理反馈', '历史预警记录'],
        output_fields: ['预警名单', '预警原因', '建议措施'],
      },
    ],
    flow_edges: [
      { from_step: 'STEP_1', to_step: 'STEP_2', reason: '逾期预测结果输入风险分层模型，细化风险分类' },
      { from_step: 'STEP_2', to_step: 'STEP_3', reason: '风险分层结果和逾期概率共同输入预警名单生成' },
    ],
    io_compatibility: {
      total_edges: 2,
      passed: 1,
      partial: 1,
      failed: 0,
      compatibility_rate: 0.7,
      'STEP_1->STEP_2': {
        matched: ['风险评分', '企业财务指标'],
        unmatched: ['行业分类（STEP_2独立需求）'],
        notes: 'STEP_2的行业分类可从企业主数据获取，不影响串联',
      },
      'STEP_2->STEP_3': {
        matched: ['风险等级', '预警等级'],
        unmatched: ['客户经理反馈（需人工输入）'],
        notes: 'STEP_3需要客户经理定期反馈，建议配套工作流工具',
      },
    },
    missing_data: ['行业景气度指数（外部数据源）'],
    expected_outputs: ['预警名单', '逾期概率', '风险分层', '预警时间窗口', '建议措施'],
    business_explanation: '这套方案按照"先预测会不会逾期→再分层哪些更紧急→最后生成预警名单"的思路工作。第一步用财务和经营数据预测企业未来逾期的可能性，第二步把企业按风险高低分层，第三步整合所有信息生成客户经理可直接使用的预警名单。',
    technical_explanation: '三步串行流程：Step1逾期预测模型（时间序列+GBDT）输出月度逾期概率；Step2风险分层模型（聚类+评分卡）将企业划分为5个风险层级；Step3名单生成模型（规则引擎+排序算法）综合各维度输出最终预警名单。各模型通过MQ异步通信，支持每日批量更新。',
    management_explanation: '该方案实现了对公贷款贷后预警的自动化闭环。从数据输入到预警名单输出全流程自动化，预计可提前30-45天发现风险信号。建议初期以逾期预测模型为核心快速上线，再逐步叠加风险分层和名单生成模块。预计实施周期8-10周。',
    usage_guide: [
      { step: 'Step 1: 部署逾期预测模型', description: '接入企业财务和经营数据，完成模型训练和验证', estimated_time: '3周', data_preparation: '历史企业财务数据、逾期标签标注' },
      { step: 'Step 2: 部署风险分层模型', description: '配置风险分层策略，与核心银行系统对接', estimated_time: '2周', data_preparation: '企业行业分类数据、风险等级定义' },
      { step: 'Step 3: 部署预警名单生成', description: '完成预警规则配置，对接客户经理工作台', estimated_time: '2周', data_preparation: '预警阈值设置、工作流配置' },
      { step: '整体上线运行', description: '试运行+效果评估+优化调整', estimated_time: '3周', data_preparation: '历史回溯验证、A/B测试' },
    ],
  };
}

function buildMarketingComposition(): CompositionResponse {
  return {
    composition_id: 'COMP_MKT_001',
    composition_name: '县域新客首贷营销组合',
    scenario: '客户营销',
    total_score: 83.8,
    nodes: [
      {
        step_id: 'STEP_1',
        step_order: 1,
        model_id: 'MKT_004',
        model_name: '首贷客户挖掘模型',
        capability: '潜客识别',
        input_fields: ['外部征信数据', '多头借贷数据', '客户行为数据'],
        output_fields: ['首贷倾向评分', '潜客排名'],
      },
      {
        step_id: 'STEP_2',
        step_order: 2,
        model_id: 'MKT_001',
        model_name: '县域新客首贷转化预测模型',
        capability: '转化预测',
        input_fields: ['客户基本信息', '历史交易流水', '征信报告', '县域宏观指标'],
        output_fields: ['转化概率', '响应评分', '客户排名'],
      },
      {
        step_id: 'STEP_3',
        step_order: 3,
        model_id: 'MKT_005',
        model_name: '营销名单排序通用模型',
        capability: '名单排序',
        input_fields: ['客户基础评分', '历史响应标签'],
        output_fields: ['排序分数', '优先级标签'],
      },
    ],
    flow_edges: [
      { from_step: 'STEP_1', to_step: 'STEP_2', reason: '潜客倾向评分作为转化预测模型的重要特征' },
      { from_step: 'STEP_2', to_step: 'STEP_3', reason: '转化概率结果输入排序模型生成最终营销名单' },
    ],
    io_compatibility: {
      total_edges: 2,
      passed: 1,
      partial: 1,
      failed: 0,
      compatibility_rate: 0.8,
      'STEP_1->STEP_2': {
        matched: ['客户基本信息', '客户评分'],
        unmatched: [],
        notes: 'STEP_1输出的首贷倾向评分可作为STEP_2的特征输入',
      },
      'STEP_2->STEP_3': {
        matched: ['转化概率', '客户评分'],
        unmatched: ['历史响应标签（需历史营销数据）'],
        notes: '历史响应标签如缺失，可使用转化概率直接排序替代',
      },
    },
    missing_data: ['县域宏观指标'],
    expected_outputs: ['Top20%营销名单', '转化概率排序', '客户优先级标签'],
    business_explanation: '这套方案按照"先找到潜在客户→再预测谁会响应→最后排序出最终名单"的流程。第一步从海量客户中识别有首贷需求的人，第二步精准预测每个人响应营销的概率，第三步按概率排序生成最终营销名单。',
    technical_explanation: '三步串行组合：Step1首贷客户挖掘模型（逻辑回归+规则）生成首贷倾向评分；Step2县域新客转化预测模型（XGBoost）输出转化概率；Step3排序模型（LambdaMART）结合多维度生成最终排序。各模型间通过特征存储共享中间结果。',
    management_explanation: '该组合方案覆盖了从潜客挖掘到最终名单生成的全流程。相比单模型，组合方案可提升营销响应率约50-80%。建议分阶段实施：先上线转化预测模型快速见效，再逐步补充潜客挖掘和排序模块。',
    usage_guide: [
      { step: 'Step 1: 部署首贷客户挖掘模型', description: '接入外部征信和客户行为数据', estimated_time: '2周', data_preparation: '外部数据源接入、潜客样本标注' },
      { step: 'Step 2: 部署转化预测模型', description: '利用银行内部数据完成模型训练', estimated_time: '3周', data_preparation: '历史营销数据整理、特征工程' },
      { step: 'Step 3: 部署排序模型', description: '配置排序策略，对接营销渠道', estimated_time: '1周', data_preparation: '排序策略配置' },
      { step: '整体上线运行', description: 'A/B测试验证效果，逐步放量', estimated_time: '2周', data_preparation: '实验设计、监控指标配置' },
    ],
  };
}

export function compositionMock(query: string): CompositionResponse {
  const q = query.toLowerCase();
  if (q.includes('农户') || q.includes('贷前') || q.includes('准入') || q.includes('欺诈')) {
    return buildCreditPreLoanComposition();
  }
  if (q.includes('预警') || q.includes('逾期') || q.includes('贷后') || q.includes('对公')) {
    return buildPostLoanWarningComposition();
  }
  return buildMarketingComposition();
}
