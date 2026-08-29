#!/usr/bin/env python3
"""Expand eval datasets to 100+ entries each."""
import json, os

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'eval')
data_dir = os.path.abspath(data_dir)

# ===== intent_eval: append 50 more =====
intents = [
    # credit_risk (30)
    ('我想知道哪些农户最有可能还不上贷款', 'credit_risk'),
    ('帮我评估这批小微企业主的信用风险水平', 'credit_risk'),
    ('做个对公客户违约概率的预测模型', 'credit_risk'),
    ('需要自动识别虚假的贷款申请材料', 'credit_risk'),
    ('贷后管理需要定期监控客户经营状况变化', 'credit_risk'),
    ('筛选出风险较高的存量贷款客户进行排查', 'credit_risk'),
    ('怎么判断一个人有没有多头借贷的风险', 'credit_risk'),
    ('信用卡客户哪些可能分期后还不上钱', 'credit_risk'),
    ('帮我们设计一套自动化的授信审批规则', 'credit_risk'),
    ('哪些担保关系可能导致风险集中爆发', 'credit_risk'),
    ('预测一下这些小微企业下季度的违约概率', 'credit_risk'),
    ('贷前需要快速判断客户是否符合准入条件', 'credit_risk'),
    ('帮我做贷款五级分类的迁徙分析', 'credit_risk'),
    ('哪些抵质押物的价值在缩水需要预警', 'credit_risk'),
    ('贷款资金有没有被挪用去炒股的迹象', 'credit_risk'),
    ('同一实控人旗下多家企业的综合风险评估', 'credit_risk'),
    ('涉农贷款的风险敞口有多大', 'credit_risk'),
    ('农户的征信和还款能力综合评估', 'credit_risk'),
    ('哪些贷款客户近期经营状况恶化', 'credit_risk'),
    ('如何识别内外勾结的骗贷团伙', 'credit_risk'),
    ('小微企业快贷产品的准入规则优化', 'credit_risk'),
    ('帮我建一个贷前反欺诈的评分模型', 'credit_risk'),
    ('想分析一下不同行业客户的违约特征差异', 'credit_risk'),
    ('帮我找出贷款用途可能造假的客户', 'credit_risk'),
    ('需要定期生成贷后风险排查名单', 'credit_risk'),
    ('有没有模型能预测信用卡客户的逾期概率', 'credit_risk'),
    ('对存量对公客户做一次全面的信用评级', 'credit_risk'),
    ('农户的还款能力和还款意愿如何评估', 'credit_risk'),
    ('帮我做一个贷中资金流向的监控方案', 'credit_risk'),
    ('如何快速识别一笔贷款申请的风险点', 'credit_risk'),
    # customer_marketing (10)
    ('怎么筛选出有贷款意向的新开户客户', 'customer_marketing'),
    ('哪些客户最近可能会流失需要做挽留', 'customer_marketing'),
    ('帮我找到潜在的高净值客户做私行营销', 'customer_marketing'),
    ('想做一批手机银行活跃客户的理财产品推荐', 'customer_marketing'),
    ('帮我分析哪些客户喜欢在线上办业务', 'customer_marketing'),
    ('想给存量客户做存款产品的精准推送', 'customer_marketing'),
    ('怎么把沉睡的信用卡客户重新激活', 'customer_marketing'),
    ('需要识别出有购房意愿的客户群体', 'customer_marketing'),
    ('帮我筛选出最适合推消费贷的客户名单', 'customer_marketing'),
    ('哪些小微企业主最近有扩大经营的资金需求', 'customer_marketing'),
    # operation_management (10)
    ('银行的网点要不要调整布局和数量', 'operation_management'),
    ('柜员排班总是有忙闲不均的情况怎么优化', 'operation_management'),
    ('ATM机什么时候需要加钞和维保预测一下', 'operation_management'),
    ('有模型能检测员工的异常操作行为吗', 'operation_management'),
    ('帮银行做智能客服的话需要哪些能力', 'operation_management'),
    ('业务流程中有没有能自动化的环节', 'operation_management'),
    ('反洗钱的交易监测规则怎么优化', 'operation_management'),
    ('帮我计算一下各网点的综合运营效率排名', 'operation_management'),
    ('银行流动性缺口的压力测试怎么搞', 'operation_management'),
    ('手机银行App上面的功能使用情况分析', 'operation_management'),
]

f = open(os.path.join(data_dir, 'intent_eval.jsonl'), 'a', encoding='utf-8')
for idx, (q, d) in enumerate(intents):
    json.dump({'test_id': f'INTENT_{51+idx:03d}', 'query': q, 'expected_intent': d, 'expected_domain': d, 'difficulty': 'medium'}, f, ensure_ascii=False)
    f.write('\n')
f.close()
print(f'intent_eval.jsonl: appended {len(intents)}')
with open(os.path.join(data_dir, 'intent_eval.jsonl'), 'r', encoding='utf-8') as ff:
    print(f'  Total: {sum(1 for _ in ff)}')

# ===== tag_eval: append 75 more =====
tags = [
    ('农户贷款准入评分', ['credit_risk', 'pre_loan', 'farmer', 'admission_scoring']),
    ('小微企业反欺诈检测', ['credit_risk', 'pre_loan', 'small_micro_enterprise', 'anti_fraud']),
    ('对公客户贷后逾期预警', ['credit_risk', 'post_loan', 'corporate', 'default_prediction', 'early_warning']),
    ('个人消费贷申请评分', ['credit_risk', 'pre_loan', 'individual', 'admission_scoring', 'consumer_loan']),
    ('信用卡分期客户风险分层', ['credit_risk', 'in_loan', 'individual', 'credit_card', 'credit_rating']),
    ('乡镇企业流动资金信用评估', ['credit_risk', 'pre_loan', 'small_micro_enterprise', 'admission_scoring']),
    ('高净值客户理财推荐', ['customer_marketing', 'pre_marketing', 'high_net_worth', 'cross_selling', 'financial_product']),
    ('老年客群存款营销', ['customer_marketing', 'pre_marketing', 'elderly', 'conversion_prediction', 'deposit']),
    ('Z世代手机银行活跃度提升', ['customer_marketing', 'in_marketing', 'young_customer', 'conversion_prediction', 'mobile_banking']),
    ('供应链核心企业上下游营销', ['customer_marketing', 'pre_marketing', 'supply_chain', 'cross_selling']),
    ('代发工资客户交叉销售', ['customer_marketing', 'in_marketing', 'existing_customer', 'cross_selling']),
    ('县域商户收单业务营销', ['customer_marketing', 'pre_marketing', 'rural_commerce', 'conversion_prediction']),
    ('农村电商客群贷款需求识别', ['customer_marketing', 'pre_marketing', 'rural_commerce', 'demand_forecasting']),
    ('客户流失挽回策略推荐', ['customer_marketing', 'post_marketing', 'churned_customer', 'churn_prediction']),
    ('财富客户综合贡献度评估', ['customer_marketing', 'performance_analysis', 'high_net_worth', 'value_assessment']),
    ('网点柜面业务量预测排班', ['operation_management', 'daily_operation', 'demand_forecasting', 'resource_optimization']),
    ('厅堂智能排队叫号优化', ['operation_management', 'daily_operation', 'priority_ranking', 'resource_optimization']),
    ('ATM现钞需求预测调配', ['operation_management', 'daily_operation', 'demand_forecasting']),
    ('柜员操作风险实时监测', ['operation_management', 'risk_management', 'anomaly_detection', 'early_warning']),
    ('大额交易反洗钱筛查', ['operation_management', 'compliance', 'anomaly_detection', 'anti_money_laundering']),
    ('客户身份识别异常报警', ['operation_management', 'risk_management', 'anomaly_detection', 'early_warning']),
    ('监管报表自动生成和校验', ['operation_management', 'compliance', 'compliance_check', 'regulatory_reporting']),
    ('内部操作合规性自动审查', ['operation_management', 'compliance', 'compliance_check']),
    ('员工离职风险预测预警', ['operation_management', 'resource_planning', 'churn_prediction', 'early_warning']),
    ('对公客户资金归集预测', ['customer_marketing', 'in_marketing', 'corporate', 'demand_forecasting']),
    ('涉农贷款风险监控与预警', ['credit_risk', 'in_loan', 'farmer', 'agricultural_loan', 'early_warning']),
    ('小微企业票据贴现需求预测', ['customer_marketing', 'pre_marketing', 'small_micro_enterprise', 'demand_forecasting']),
    ('信用卡套现行为识别模型', ['credit_risk', 'in_loan', 'individual', 'credit_card', 'anomaly_detection']),
    ('农户种植周期资金缺口预测', ['customer_marketing', 'pre_marketing', 'farmer', 'demand_forecasting', 'agricultural_loan']),
    ('担保圈风险传染路径分析', ['credit_risk', 'risk_management', 'guarantee_circle', 'anomaly_detection']),
    ('不良贷款清收优先级排序', ['credit_risk', 'post_loan', 'priority_ranking']),
    ('银行网点转型选址评估', ['operation_management', 'resource_planning', 'demand_forecasting']),
    ('客户活动参与意愿度预测', ['customer_marketing', 'pre_marketing', 'existing_customer', 'response_prediction']),
    ('小微企业主个人信用辅助评估', ['credit_risk', 'pre_loan', 'small_micro_enterprise', 'credit_rating']),
    ('存款产品客户需求匹配', ['customer_marketing', 'pre_marketing', 'individual', 'preference_analysis', 'deposit']),
    ('对公客户行业风险敞口分析', ['credit_risk', 'risk_management', 'corporate', 'admission_scoring']),
    ('手机银行渠道客户分流策略', ['operation_management', 'daily_operation', 'individual', 'preference_analysis', 'mobile_banking']),
    ('农村承包经营权抵押贷款评估', ['credit_risk', 'pre_loan', 'farmer', 'admission_scoring', 'agricultural_loan']),
    ('银发客群养老金融产品推荐', ['customer_marketing', 'pre_marketing', 'elderly', 'cross_selling', 'pension_finance']),
    ('信贷审批流程时效分析优化', ['operation_management', 'performance_analysis', 'anomaly_detection']),
    ('客户满意度影响因素分析', ['operation_management', 'performance_analysis', 'individual', 'value_assessment']),
    ('银行员工绩效智能评估模型', ['operation_management', 'performance_analysis', 'resource_planning', 'value_assessment']),
    ('新客开户后金融产品推荐', ['customer_marketing', 'post_marketing', 'new_customer', 'cross_selling']),
    ('客户生命周期阶段活跃度预测', ['customer_marketing', 'performance_analysis', 'existing_customer', 'lifetime_value']),
    ('信用卡客户消费行为分类', ['customer_marketing', 'in_marketing', 'individual', 'segmentation', 'credit_card']),
    ('企业税务信息与贷款风险评估', ['credit_risk', 'pre_loan', 'corporate', 'admission_scoring']),
    ('区域经济指标与银行贷款策略', ['credit_risk', 'risk_management', 'corporate', 'admission_scoring']),
    ('线上贷款产品反欺诈模型', ['credit_risk', 'pre_loan', 'individual', 'anti_fraud']),
    ('客户主动还款意愿度分析', ['credit_risk', 'in_loan', 'existing_customer', 'admission_scoring']),
    ('对公客户财务报表智能解读', ['credit_risk', 'pre_loan', 'corporate', 'credit_rating']),
    ('农户经营收益波动预测', ['credit_risk', 'in_loan', 'farmer', 'demand_forecasting', 'agricultural_loan']),
    ('银行自助设备故障预测维护', ['operation_management', 'daily_operation', 'anomaly_detection', 'early_warning']),
    ('客户流失前行为特征识别', ['customer_marketing', 'post_marketing', 'churned_customer', 'churn_prediction', 'early_warning']),
    ('千企万户走访普惠营销名单排序', ['customer_marketing', 'pre_marketing', 'small_micro_enterprise', 'priority_ranking']),
    ('银行中间业务收入增长点预测', ['operation_management', 'performance_analysis', 'demand_forecasting']),
    ('客户投诉自动分类和路由', ['operation_management', 'daily_operation', 'priority_ranking']),
    ('抵质押品动态价值监测', ['credit_risk', 'in_loan', 'risk_management', 'early_warning']),
    ('企业上下游产业链交易分析', ['credit_risk', 'pre_loan', 'supply_chain', 'credit_rating']),
    ('粮食种植户贷款需求季节预测', ['customer_marketing', 'pre_marketing', 'farmer', 'demand_forecasting', 'agricultural_loan']),
    ('社保公积金数据信贷评估应用', ['credit_risk', 'pre_loan', 'individual', 'admission_scoring']),
    ('外贸企业汇率风险与信贷风险', ['credit_risk', 'risk_management', 'corporate', 'admission_scoring']),
    ('县域银行服务点布局优化', ['operation_management', 'resource_planning', 'rural_commerce', 'resource_optimization']),
    ('银行客户之声舆情监测分析', ['operation_management', 'risk_management', 'anomaly_detection', 'early_warning']),
    ('科技型企业知识产权质押评估', ['credit_risk', 'pre_loan', 'small_micro_enterprise', 'credit_rating']),
    ('零售客户AUM增长预测', ['customer_marketing', 'performance_analysis', 'individual', 'value_assessment']),
    ('不良资产清收效果预测', ['credit_risk', 'post_loan', 'priority_ranking', 'default_prediction']),
    ('银行厅堂营销互动转化分析', ['customer_marketing', 'in_marketing', 'new_customer', 'conversion_prediction']),
    ('企业ESG评分与信用风险关联', ['credit_risk', 'pre_loan', 'corporate', 'credit_rating']),
    ('睡眠户激活营销活动设计', ['customer_marketing', 'pre_marketing', 'dormant_customer', 'conversion_prediction']),
    ('银行网点无纸化转型效果分析', ['operation_management', 'performance_analysis', 'resource_optimization']),
    ('公积金缴存客户消费贷预授信', ['credit_risk', 'pre_loan', 'individual', 'admission_scoring', 'consumer_loan']),
    ('客户经理包片营销任务分配', ['customer_marketing', 'pre_marketing', 'resource_optimization', 'priority_ranking']),
    ('银行IT系统运行异常预警', ['operation_management', 'risk_management', 'anomaly_detection', 'early_warning']),
    ('对公客户存款流失前兆识别', ['customer_marketing', 'post_marketing', 'corporate', 'churn_prediction', 'early_warning']),
    ('县域特色产业金融服务方案', ['customer_marketing', 'pre_marketing', 'rural_area', 'cross_selling', 'agricultural_loan']),
]

f = open(os.path.join(data_dir, 'tag_eval.jsonl'), 'a', encoding='utf-8')
for idx, (q, t) in enumerate(tags):
    json.dump({'test_id': f'TAG_{21+idx:03d}', 'query': q, 'expected_tags': t, 'difficulty': 'medium'}, f, ensure_ascii=False)
    f.write('\n')
f.close()
print(f'tag_eval.jsonl: appended {len(tags)}')
with open(os.path.join(data_dir, 'tag_eval.jsonl'), 'r', encoding='utf-8') as ff:
    print(f'  Total: {sum(1 for _ in ff)}')

# ===== topk_eval: append 90 more =====
topks = [
    ('农户贷款准入和反欺诈', ['RISK_001', 'RISK_002']),
    ('小微企业贷款全流程风控', ['RISK_004', 'RISK_005', 'RISK_006']),
    ('对公客户信用评级违约预测', ['RISK_007', 'RISK_008']),
    ('个人消费贷信用评分', ['RISK_010', 'RISK_011']),
    ('信用卡逾期风险评分', ['RISK_012', 'OPS_015']),
    ('新客首贷转化营销', ['MKT_001', 'MKT_002', 'MKT_005']),
    ('存量客户交叉销售', ['MKT_003', 'MKT_004', 'MKT_007']),
    ('客户流失预测与沉睡唤醒', ['MKT_009', 'MKT_008']),
    ('网点客流预测智能排班', ['OPS_001', 'OPS_002', 'OPS_003']),
    ('反洗钱可疑交易监测', ['OPS_009', 'OPS_010', 'OPS_011']),
    ('精准营销客群筛选响应预测', ['MKT_005', 'MKT_006', 'MKT_020']),
    ('贷后风险排查和预警', ['RISK_017', 'RISK_008', 'RISK_015']),
    ('流动性风险预测', ['OPS_023', 'OPS_025']),
    ('智能客服投诉分析', ['OPS_020', 'OPS_019', 'OPS_021']),
    ('合规制度匹配监管报表', ['OPS_012', 'OPS_014', 'OPS_034']),
    ('农户小额贷款反欺诈准入评估', ['RISK_001', 'RISK_002', 'RISK_003']),
    ('对公贷款贷后监控预警', ['RISK_008', 'RISK_009', 'RISK_024']),
    ('小微企业贷前准入风控', ['RISK_004', 'RISK_005']),
    ('客户营销响应预测名单排序', ['MKT_005', 'MKT_006']),
    ('县域新客首贷白名单推荐', ['MKT_001', 'MKT_025']),
    ('存量客户价值分层', ['MKT_007', 'MKT_010']),
    ('网点运营效率提升', ['OPS_001', 'OPS_002', 'OPS_005']),
    ('反欺诈和操作风险监测', ['RISK_016', 'OPS_008', 'OPS_009']),
    ('个人信用卡风险评分', ['RISK_012', 'RISK_017']),
    ('存款流失预警和挽回', ['MKT_009', 'MKT_018']),
    ('担保圈和关联企业风险', ['RISK_013', 'RISK_014']),
    ('普惠小微企业营销', ['MKT_026', 'MKT_004']),
    ('员工操作和绩效评估', ['OPS_030', 'OPS_016']),
    ('贷款用途异常监控', ['RISK_015', 'RISK_023']),
    ('农产品价格波动对还贷影响', ['RISK_030', 'RISK_025']),
    ('客户渠道偏好手机银行推荐', ['MKT_020', 'MKT_015']),
    ('应急资金准备金优化', ['OPS_023', 'OPS_005']),
    ('贷款申请真实性格审核', ['RISK_035', 'RISK_002']),
    ('县域商圈商户营销', ['MKT_024', 'MKT_032']),
    ('柜面业务异常交易监控', ['OPS_008', 'OPS_029']),
    ('企业主个人信用辅助评估', ['RISK_032', 'RISK_004']),
    ('理财产品偏好推荐', ['MKT_017', 'MKT_004']),
    ('网点选址和资源配置', ['OPS_002', 'OPS_004']),
    ('共同借款人多头借贷识别', ['RISK_033', 'RISK_016']),
    ('农户季节性融资需求', ['MKT_033', 'MKT_011']),
    ('客户身份核验异常检测', ['OPS_027', 'RISK_002']),
    ('贷前综合准入评分', ['RISK_001', 'RISK_031', 'RISK_035']),
    ('企业开户营销转化', ['MKT_002', 'MKT_031']),
    ('逾期客户催收策略优化', ['RISK_024', 'RISK_026']),
    ('大额交易洗钱风险', ['OPS_009', 'OPS_026']),
    ('不良贷款预警名单生成', ['RISK_025', 'RISK_034']),
    ('员工考勤排班优化', ['OPS_004', 'OPS_017']),
    ('小微企业主贷款需求', ['MKT_012', 'MKT_034']),
    ('抵押物价值波动风险', ['RISK_021', 'RISK_028']),
    ('智能客服工单分配', ['OPS_022', 'OPS_019']),
    ('手机银行活跃度提升营销', ['MKT_015', 'MKT_022']),
    ('运营管理驾驶舱指标', ['OPS_035', 'OPS_025']),
    ('对账异常和风险识别', ['OPS_033', 'RISK_016']),
    ('省份区域信贷风险预警', ['RISK_029', 'RISK_028']),
    ('农业龙头企业经营风险', ['RISK_030', 'RISK_005']),
    ('客户经理销售机会推荐', ['MKT_030', 'MKT_029']),
    ('新市民金融服务需求', ['MKT_024', 'RISK_031']),
    ('内部流程合规检查自动化', ['OPS_034', 'OPS_031']),
    ('信用卡分期营销转化', ['MKT_016', 'MKT_021']),
    ('放款审批流程优化', ['OPS_019', 'OPS_020']),
    ('跨产品智能推荐引擎', ['MKT_029', 'MKT_003']),
    ('客户风险分层管理', ['RISK_026', 'RISK_018']),
    ('电子渠道登录异常检测', ['OPS_028', 'RISK_002']),
    ('粮食种植户贷款需求', ['MKT_033', 'RISK_030']),
    ('存款增长潜力预测', ['MKT_019', 'MKT_028']),
    ('供应链金融风险识别', ['RISK_014', 'RISK_013']),
    ('反洗钱团伙网络分析', ['OPS_010', 'OPS_026']),
    ('客户流失早预警', ['MKT_009', 'MKT_010']),
    ('行业系统性风险预警', ['RISK_028', 'RISK_014']),
    ('网点金融便民服务优化', ['OPS_001', 'OPS_024']),
    ('县域农村电商客群识别', ['MKT_032', 'MKT_024']),
    ('不良贷款可回收性评估', ['RISK_019', 'RISK_018']),
    ('印章使用风险监控', ['OPS_031', 'OPS_008']),
    ('授信审批时效分析', ['OPS_019', 'RISK_027']),
    ('客户金融产品联合推荐', ['MKT_003', 'MKT_017']),
    ('涉农信用风险综合评估', ['RISK_030', 'RISK_001']),
    ('柜面授权审批违规监控', ['OPS_029', 'OPS_030']),
    ('首贷户持续关系经营', ['MKT_025', 'MKT_027']),
    ('经济波动下贷款损失预测', ['RISK_019', 'RISK_025']),
    ('支付交易实时风控拦截', ['RISK_022', 'OPS_009']),
    ('社区银行精准服务推荐', ['MKT_023', 'MKT_031']),
    ('银行外包人员操作风险', ['OPS_030', 'RISK_022']),
    ('银企合作批量获客转化', ['MKT_031', 'MKT_013']),
    ('信贷资产质量迁徙分析', ['RISK_025', 'RISK_026']),
    ('客户活跃度和睡眠预警', ['MKT_008', 'MKT_010']),
    ('互联网金融产品接入评估', ['OPS_013', 'RISK_006']),
    ('农民工工资支付风险监控', ['RISK_015', 'OPS_033']),
    ('三方支付商户风险评估', ['RISK_006', 'OPS_009']),
    ('企业经营连续性压力测试', ['RISK_005', 'RISK_028']),
    ('网点综合盈利能力评估', ['OPS_024', 'OPS_016']),
]

f = open(os.path.join(data_dir, 'topk_eval.jsonl'), 'a', encoding='utf-8')
for idx, (q, mids) in enumerate(topks):
    k = 5 if len(mids) >= 3 else 3
    json.dump({'test_id': f'TOPK_{16+idx:03d}', 'query': q, 'expected_model_ids': mids, 'k': k, 'scenario': '综合'}, f, ensure_ascii=False)
    f.write('\n')
f.close()
print(f'topk_eval.jsonl: appended {len(topks)}')
with open(os.path.join(data_dir, 'topk_eval.jsonl'), 'r', encoding='utf-8') as ff:
    print(f'  Total: {sum(1 for _ in ff)}')

# Final counts
print('\n=== Final counts ===')
for fn in ['intent_eval.jsonl', 'tag_eval.jsonl', 'topk_eval.jsonl']:
    with open(os.path.join(data_dir, fn), 'r', encoding='utf-8') as ff:
        c = sum(1 for _ in ff)
    status = 'OK' if c >= 100 else f'NEED {100-c} more'
    print(f'{fn}: {c} {status}')
