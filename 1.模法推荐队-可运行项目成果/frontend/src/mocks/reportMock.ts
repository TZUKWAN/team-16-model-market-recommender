import type { ReportRequest, ReportData } from '../types';

export function reportMock(request: ReportRequest): ReportData {
  const raw = request.demand_raw ?? '';
  const q = raw.toLowerCase();

  // Credit pre-loan report
  if (q.includes('农户') || q.includes('贷前') || q.includes('准入') || q.includes('欺诈')) {
    return {
      report_id: 'RPT-CREDIT-PRE-001',
      request_id: request.request_id ?? 'req-report-credit-pre',
      generated_at: new Date().toISOString(),
      format: request.format ?? 'markdown',
      title: '模型推荐报告 - 农户小额贷款贷前准入',
      summary: '针对农户小额贷款贷前准入风控需求，推荐反欺诈、准入评分和额度测算组合方案。',
      sections: [],
      raw_content: '',
      user_demand: raw,
      system_understanding: {
        intent: 'credit_pre_loan_risk_control',
        domain: '信贷风控',
        scenario: '农户小额贷款贷前准入',
        tags: ['农户贷款', '贷前准入', '反欺诈', '额度测算', '小额贷款'],
        translation: '业务需求"农户小额贷款贷前准入风控"对应模型任务类型为"反欺诈评分""信用评分"和"额度测算"，属于分类与回归问题。',
      },
      top3_models: [
        { rank: 1, model_name: '农户反欺诈评分模型', score: 93.2, reason: '专为农户贷款反欺诈设计，欺诈识别率92%' },
        { rank: 2, model_name: '农户准入评分模型', score: 89.5, reason: '定制化农户准入评分，区分度优秀' },
        { rank: 3, model_name: '小额贷款额度测算模型', score: 87.8, reason: '精准输出额度建议，匹配需求' },
      ],
      best_composition: {
        name: '农户小额贷款贷前准入组合',
        score: 86.5,
        steps: ['反欺诈评分 → 准入评分 → 额度测算'],
      },
      required_data: ['农户身份信息', '设备信息', '关系网络数据', '多头借贷数据', '征信报告', '农业生产数据', '经营流水', '收入证明'],
      data_gaps: ['农业生产数据（季节因素更新）', '行业景气度指数'],
      implementation_steps: [
        'Step 1: 部署反欺诈模型，对接申请渠道，采集设备指纹',
        'Step 2: 部署准入评分模型，接入征信和农业生产数据',
        'Step 3: 部署额度测算模型，配置额度策略',
        'Step 4: 全流程串联测试，A/B对比实验',
        'Step 5: 逐步放量上线，持续监控效果',
      ],
      risk_tips: [
        '反欺诈模型误报可能导致优质客户流失，建议设置人工复核通道',
        '额度测算结果仅供参考，最终审批需结合银行信贷政策',
        '农户数据质量可能影响模型效果，建议建立数据质量监控机制',
        '模型需要定期迭代更新以保持效果稳定',
      ],
    };
  }

  // Post-loan warning report
  if (q.includes('预警') || q.includes('逾期') || q.includes('贷后') || q.includes('对公')) {
    return {
      report_id: 'RPT-PLW-001',
      request_id: request.request_id ?? 'req-report-plw',
      generated_at: new Date().toISOString(),
      format: request.format ?? 'markdown',
      title: '模型推荐报告 - 对公贷款贷后预警',
      summary: '针对对公贷款贷后预警需求，推荐逾期预测、风险分层和预警名单生成组合方案。',
      sections: [],
      raw_content: '',
      user_demand: raw,
      system_understanding: {
        intent: 'post_loan_early_warning',
        domain: '信贷风控',
        scenario: '对公贷款贷后逾期预警',
        tags: ['对公贷款', '贷后预警', '逾期预测', '风险分层', '预警名单'],
        translation: '业务需求"对公贷款贷后逾期预警"对应模型任务类型为"违约预测"和"风险分层"，属于分类与排序问题。',
      },
      top3_models: [
        { rank: 1, model_name: '对公贷款逾期预测模型', score: 92.8, reason: '专为对公贷款逾期预测设计，提前预警准确率89%' },
        { rank: 2, model_name: '企业风险分层模型', score: 88.3, reason: '精细化风险分层，匹配预警名单需求' },
        { rank: 3, model_name: '企业信用风险监测模型', score: 85.6, reason: '持续性信用监测，常态化预警工具' },
      ],
      best_composition: {
        name: '对公贷款贷后预警组合',
        score: 85.2,
        steps: ['逾期预测 → 风险分层 → 预警名单'],
      },
      required_data: ['企业财务报表', '经营流水', '行业数据', '历史还款记录', '企业财务数据', '行业分类'],
      data_gaps: ['行业景气度指数（外部数据源）'],
      implementation_steps: [
        'Step 1: 部署逾期预测模型，接入企业财务和经营数据',
        'Step 2: 部署风险分层模型，配置分层策略',
        'Step 3: 部署预警名单生成模型，对接客户经理工作台',
        'Step 4: 配置预警阈值和通知规则',
        'Step 5: 试运行验证，优化模型参数',
      ],
      risk_tips: [
        '预警信号可能存在滞后，建议结合客户经理现场尽调综合判断',
        '模型需要定期基于最新逾期数据进行再训练',
        '预警名单需设置分级响应机制，避免预警疲劳',
        '企业财务数据披露频率可能影响预警时效性',
      ],
    };
  }

  // Default marketing report
  return {
    report_id: 'RPT-MKT-001',
    request_id: request.request_id ?? 'req-report-mkt',
    generated_at: new Date().toISOString(),
    format: request.format ?? 'markdown',
    title: '模型推荐报告 - 县域新客首贷营销',
    summary: '针对县域新客首贷营销需求，推荐转化预测、响应预测和营销名单排序组合方案。',
    sections: [],
    raw_content: '',
    user_demand: raw,
    system_understanding: {
      intent: 'customer_marketing',
      domain: '客户营销',
      scenario: '县域新客首贷营销',
      tags: ['新客', '首贷', '营销转化', '响应预测'],
      translation: '业务需求"筛选县域新客做首贷营销"对应模型任务类型为"客户响应预测"和"转化概率估算"，属于分类与排序问题。',
    },
    top3_models: [
      { rank: 1, model_name: '县域新客首贷转化预测模型', score: 91.5, reason: '专为县域新客首贷营销场景设计，AUC达0.87' },
      { rank: 2, model_name: '新客响应率预测模型', score: 87.2, reason: '聚焦新客响应预测，3家银行验证经验' },
      { rank: 3, model_name: '零售客户响应预测模型', score: 84.8, reason: '通用零售模型，覆盖范围广' },
    ],
    best_composition: {
      name: '县域新客首贷营销组合',
      score: 83.8,
      steps: ['潜客识别 → 转化预测 → 名单排序'],
    },
    required_data: ['客户基本信息', '历史交易流水', '征信报告', '县域宏观指标', '外部征信数据'],
    data_gaps: ['县域宏观指标', '外部征信数据（部分）'],
    implementation_steps: [
      'Step 1: 收集客户画像和交易流水数据',
      'Step 2: 部署首贷转化预测模型',
      'Step 3: 生成营销名单并排序',
      'Step 4: 对接营销渠道执行营销活动',
      'Step 5: 收集营销反馈数据优化模型',
    ],
      risk_tips: [
        '模型预测结果基于历史数据，市场环境变化可能影响预测准确性',
        '新客营销需注意用户隐私保护和营销合规要求',
        '建议设置最小测试样本验证模型实际效果再大规模推广',
        '营销名单可结合人工经验进行调整，不宜完全依赖模型',
      ],
    };
  }
