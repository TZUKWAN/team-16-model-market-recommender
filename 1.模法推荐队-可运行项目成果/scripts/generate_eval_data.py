#!/usr/bin/env python3
"""Generate B-11 eval data files: intent_eval.jsonl, tag_eval.jsonl, topk_eval.jsonl, explanation_survey_mock.json"""
import json
import os
import random

EVAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eval")
os.makedirs(EVAL_DIR, exist_ok=True)
random.seed(42)

# ============================================================
# intent_eval.jsonl - Intent classification test cases
# ============================================================
INTENT_EVAL = [
    {"test_id": "INTENT_001", "query": "我想评估农户的信用风险，看看他们能不能按时还贷", "expected_intent": "credit_risk_assessment", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_002", "query": "怎么识别贷款申请中的欺诈行为？防止有人骗贷", "expected_intent": "anti_fraud", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_003", "query": "农户申请贷款，系统能不能自动算出建议的贷款额度", "expected_intent": "amount_calculation", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_004", "query": "小微企业来贷款，需要快速知道他们够不够准入条件", "expected_intent": "credit_risk_assessment", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_005", "query": "评估一下企业的经营流水稳不稳定，有没有异常波动", "expected_intent": "business_stability_analysis", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_006", "query": "小微企业提供的资料会不会是假的？怎么识别伪造的流水", "expected_intent": "anti_fraud", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_007", "query": "对公客户需要做个信用评级，根据财务报表给出信用等级", "expected_intent": "credit_rating", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_008", "query": "贷款放出去之后，怎么监控企业的经营情况？有风险早点报警", "expected_intent": "risk_monitoring", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_009", "query": "怎么预测一个企业客户到期会不会违约？需要一个违约概率", "expected_intent": "default_prediction", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_010", "query": "个人来申请消费贷，能不能自动评估他的信用状况和还款能力", "expected_intent": "credit_rating", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_011", "query": "申请消费贷的人里面有没有身份被盗用的？需要反欺诈筛查", "expected_intent": "anti_fraud", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_012", "query": "信用卡客户哪些人可能会逾期？想提前识别做干预", "expected_intent": "default_prediction", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_013", "query": "小微企业互相担保形成了担保圈，风险会不会传导？怎么分析", "expected_intent": "risk_network_analysis", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_014", "query": "集团旗下的关联企业很多，怎么识别关联关系和整体风险", "expected_intent": "risk_network_analysis", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_015", "query": "贷了款之后客户把钱用到哪去了？能不能监控资金流向防挪用", "expected_intent": "risk_monitoring", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_016", "query": "同时在多家机构借钱的客户风险高，怎么识别多头借贷的人", "expected_intent": "risk_network_analysis", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_017", "query": "存量贷款客户要做定期排查，哪些人风险上升了需要关注", "expected_intent": "risk_monitoring", "expected_domain": "credit_risk", "difficulty": "easy"},
    {"test_id": "INTENT_018", "query": "客户的违约概率PD怎么做？需要一个标准的PD模型", "expected_intent": "default_prediction", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_019", "query": "违约之后损失率LGD怎么算？不同担保措施下损失率不一样", "expected_intent": "loss_given_default", "expected_domain": "credit_risk", "difficulty": "hard"},
    {"test_id": "INTENT_020", "query": "想根据客户的风险等级给出不同的贷款利率，怎么做风险定价", "expected_intent": "risk_pricing", "expected_domain": "credit_risk", "difficulty": "medium"},
    {"test_id": "INTENT_021", "query": "新客户在县域开户了，怎么筛选出可能有贷款需求的人做营销", "expected_intent": "marketing_targeting", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_022", "query": "新开卡的客户怎么知道谁最近可能需要贷款？识别贷款意向", "expected_intent": "intent_recognition", "expected_domain": "customer_marketing", "difficulty": "medium"},
    {"test_id": "INTENT_023", "query": "老客户还能买点什么别的产品？想推荐存款理财贷款等", "expected_intent": "cross_selling", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_024", "query": "客户喜欢存款还是理财？喜欢线上还是线下？分析一下偏好", "expected_intent": "preference_analysis", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_025", "query": "营销活动发出去之前，哪些客户最可能响应？筛选高响应客群", "expected_intent": "response_prediction", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_026", "query": "不同客户适合用什么渠道触达？电话、短信还是APP推送", "expected_intent": "channel_optimization", "expected_domain": "customer_marketing", "difficulty": "medium"},
    {"test_id": "INTENT_027", "query": "客户里面哪些是高价值客户？怎么分层和识别", "expected_intent": "value_assessment", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_028", "query": "很多客户长时间没交易沉睡了，怎么筛选可能唤醒的人", "expected_intent": "customer_reactivation", "expected_domain": "customer_marketing", "difficulty": "medium"},
    {"test_id": "INTENT_029", "query": "客户最近流失很多，能不能提前预测哪些人要流失", "expected_intent": "churn_prediction", "expected_domain": "customer_marketing", "difficulty": "easy"},
    {"test_id": "INTENT_030", "query": "客户从新客到成熟到流失，怎么识别在哪个生命周期阶段", "expected_intent": "lifecycle_management", "expected_domain": "customer_marketing", "difficulty": "medium"},
    {"test_id": "INTENT_031", "query": "银行网点的客流量波动大，能不能预测每天的客流好排班", "expected_intent": "workforce_management", "expected_domain": "operation_management", "difficulty": "easy"},
    {"test_id": "INTENT_032", "query": "柜员排班总是不合理，有没有智能排班的工具", "expected_intent": "workforce_management", "expected_domain": "operation_management", "difficulty": "easy"},
    {"test_id": "INTENT_033", "query": "网点各项业务量怎么预测？方便提前安排窗口和资源", "expected_intent": "workforce_management", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_034", "query": "网点布在哪里最合适？新设或迁址需要数据支撑", "expected_intent": "branch_planning", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_035", "query": "怎么评价每个网点的综合运营效率？从多维度打分排名", "expected_intent": "performance_evaluation", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_036", "query": "很多柜面业务其实可以在机器上办，怎么引导客户分流", "expected_intent": "process_optimization", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_037", "query": "ATM老是出故障，能不能提前预测故障提前维护", "expected_intent": "it_operations", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_038", "query": "交易流水里哪些可能是洗钱行为？自动识别可疑交易", "expected_intent": "aml_compliance", "expected_domain": "operation_management", "difficulty": "easy"},
    {"test_id": "INTENT_039", "query": "按反洗钱要求要给客户做洗钱风险评级，能自动化吗", "expected_intent": "aml_compliance", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_040", "query": "多账户频繁转账可能涉及洗钱，怎么挖掘这种团伙关系", "expected_intent": "aml_compliance", "expected_domain": "operation_management", "difficulty": "hard"},
    {"test_id": "INTENT_041", "query": "业务操作是否符合内部合规制度？能不能自动检查", "expected_intent": "compliance_management", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_042", "query": "柜员和客户经理的操作行为有没有异常？自动监测预警", "expected_intent": "risk_monitoring", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_043", "query": "监管报表每月都要报，能不能从系统自动取数生成", "expected_intent": "compliance_management", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_044", "query": "手机银行上的交易怎么实时识别和拦截欺诈", "expected_intent": "anti_fraud", "expected_domain": "operation_management", "difficulty": "easy"},
    {"test_id": "INTENT_045", "query": "客户投诉越来越多，能不能自动分类和分析根因", "expected_intent": "customer_service", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_046", "query": "想做个智能客服，客户提问后自动匹配FAQ答案", "expected_intent": "customer_service", "expected_domain": "operation_management", "difficulty": "easy"},
    {"test_id": "INTENT_047", "query": "IT工单业务工单怎么自动分给最合适的人处理", "expected_intent": "workflow_optimization", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_048", "query": "银行短期流动性缺口怎么提前预测？防止流动性风险", "expected_intent": "treasury_management", "expected_domain": "operation_management", "difficulty": "hard"},
    {"test_id": "INTENT_049", "query": "贷款利率怎么定才合理？覆盖风险成本又有竞争力", "expected_intent": "risk_pricing", "expected_domain": "operation_management", "difficulty": "medium"},
    {"test_id": "INTENT_050", "query": "核心岗位的员工会不会离职？怎么提前预警", "expected_intent": "workforce_management", "expected_domain": "operation_management", "difficulty": "medium"},
]

intent_path = os.path.join(EVAL_DIR, "intent_eval.jsonl")
with open(intent_path, "w", encoding="utf-8") as f:
    for item in INTENT_EVAL:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
print(f"[B-11] Created {intent_path} with {len(INTENT_EVAL)} test cases")

# ============================================================
# tag_eval.jsonl - Tag recommendation evaluation
# ============================================================
TAG_EVAL = [
    {"test_id": "TAG_001", "query": "农户小额贷款准入评估", "expected_tags": ["credit_risk", "pre_loan", "farmer", "admission_scoring"], "difficulty": "easy"},
    {"test_id": "TAG_002", "query": "小微企业流水真实性核验", "expected_tags": ["credit_risk", "pre_loan", "small_micro_enterprise", "anti_fraud"], "difficulty": "medium"},
    {"test_id": "TAG_003", "query": "对公客户信用等级评定", "expected_tags": ["credit_risk", "pre_loan", "corporate", "credit_rating"], "difficulty": "easy"},
    {"test_id": "TAG_004", "query": "信用卡逾期风险预测", "expected_tags": ["credit_risk", "in_loan", "individual", "default_prediction", "credit_card"], "difficulty": "easy"},
    {"test_id": "TAG_005", "query": "担保圈关联风险分析", "expected_tags": ["credit_risk", "post_loan", "guarantee_circle", "anomaly_detection"], "difficulty": "medium"},
    {"test_id": "TAG_006", "query": "新开户客户首贷营销", "expected_tags": ["customer_marketing", "pre_marketing", "new_customer", "conversion_prediction", "first_loan"], "difficulty": "easy"},
    {"test_id": "TAG_007", "query": "存量客户理财推荐", "expected_tags": ["customer_marketing", "in_marketing", "existing_customer", "cross_selling", "financial_product"], "difficulty": "easy"},
    {"test_id": "TAG_008", "query": "客户流失预警与挽留", "expected_tags": ["customer_marketing", "post_marketing", "existing_customer", "churn_prediction"], "difficulty": "easy"},
    {"test_id": "TAG_009", "query": "网点客流预测与排班", "expected_tags": ["operation_management", "daily_operation", "demand_forecasting", "resource_optimization"], "difficulty": "easy"},
    {"test_id": "TAG_010", "query": "反洗钱可疑交易监测", "expected_tags": ["operation_management", "risk_management", "anomaly_detection", "anti_money_laundering"], "difficulty": "easy"},
    {"test_id": "TAG_011", "query": "小微企业经营稳定性评分", "expected_tags": ["credit_risk", "pre_loan", "small_micro_enterprise", "admission_scoring"], "difficulty": "medium"},
    {"test_id": "TAG_012", "query": "手机银行活跃度提升", "expected_tags": ["customer_marketing", "in_marketing", "individual", "conversion_prediction", "mobile_banking"], "difficulty": "medium"},
    {"test_id": "TAG_013", "query": "智能客服FAQ机器人", "expected_tags": ["operation_management", "daily_operation", "individual", "preference_analysis"], "difficulty": "medium"},
    {"test_id": "TAG_014", "query": "贷款审批任务自动分配", "expected_tags": ["operation_management", "daily_operation", "priority_ranking", "resource_optimization"], "difficulty": "medium"},
    {"test_id": "TAG_015", "query": "理财产品偏好分析", "expected_tags": ["customer_marketing", "pre_marketing", "individual", "preference_analysis", "financial_product"], "difficulty": "easy"},
    {"test_id": "TAG_016", "query": "农户经营周期性资金需求", "expected_tags": ["customer_marketing", "pre_marketing", "farmer", "rural_area", "demand_forecasting"], "difficulty": "hard"},
    {"test_id": "TAG_017", "query": "监管报表数据质量监控", "expected_tags": ["operation_management", "compliance", "anomaly_detection", "compliance_check", "regulatory_reporting"], "difficulty": "hard"},
    {"test_id": "TAG_018", "query": "客户综合贡献度评估", "expected_tags": ["customer_marketing", "performance_analysis", "existing_customer", "value_assessment"], "difficulty": "medium"},
    {"test_id": "TAG_019", "query": "贷款资金流向异常监控", "expected_tags": ["credit_risk", "in_loan", "anomaly_detection", "early_warning"], "difficulty": "medium"},
    {"test_id": "TAG_020", "query": "员工离职风险预测", "expected_tags": ["operation_management", "resource_planning", "churn_prediction", "early_warning"], "difficulty": "medium"},
]

tag_path = os.path.join(EVAL_DIR, "tag_eval.jsonl")
with open(tag_path, "w", encoding="utf-8") as f:
    for item in TAG_EVAL:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
print(f"[B-11] Created {tag_path} with {len(TAG_EVAL)} test cases")

# ============================================================
# topk_eval.jsonl - Top-K model recommendation evaluation
# ============================================================
TOP_K_EVAL = [
    {"test_id": "TOPK_001", "query": "农户贷款准入评估和反欺诈", "expected_model_ids": ["RISK_001", "RISK_002"], "k": 3, "scenario": "农户贷款"},
    {"test_id": "TOPK_002", "query": "小微企业贷款全流程风控", "expected_model_ids": ["RISK_004", "RISK_005", "RISK_006"], "k": 5, "scenario": "小微贷款"},
    {"test_id": "TOPK_003", "query": "对公客户信用评级和违约预测", "expected_model_ids": ["RISK_007", "RISK_009"], "k": 3, "scenario": "对公风控"},
    {"test_id": "TOPK_004", "query": "个人消费贷信用评分", "expected_model_ids": ["RISK_010", "RISK_011"], "k": 3, "scenario": "消费贷"},
    {"test_id": "TOPK_005", "query": "信用卡逾期风险评分", "expected_model_ids": ["RISK_012", "OPS_015"], "k": 3, "scenario": "信用卡"},
    {"test_id": "TOPK_006", "query": "新客首贷转化营销", "expected_model_ids": ["MKT_001", "MKT_002", "MKT_005"], "k": 5, "scenario": "新客营销"},
    {"test_id": "TOPK_007", "query": "存量客户交叉销售", "expected_model_ids": ["MKT_003", "MKT_004", "MKT_007"], "k": 5, "scenario": "交叉销售"},
    {"test_id": "TOPK_008", "query": "客户流失预测与沉睡唤醒", "expected_model_ids": ["MKT_009", "MKT_008"], "k": 3, "scenario": "客户留存"},
    {"test_id": "TOPK_009", "query": "网点客流预测和智能排班", "expected_model_ids": ["OPS_001", "OPS_002", "OPS_003"], "k": 5, "scenario": "网点运营"},
    {"test_id": "TOPK_010", "query": "反洗钱可疑交易监测", "expected_model_ids": ["OPS_009", "OPS_010", "OPS_011"], "k": 5, "scenario": "反洗钱"},
    {"test_id": "TOPK_011", "query": "精准营销客群筛选和响应预测", "expected_model_ids": ["MKT_005", "MKT_006", "MKT_020"], "k": 5, "scenario": "精准营销"},
    {"test_id": "TOPK_012", "query": "贷后风险排查和预警", "expected_model_ids": ["RISK_017", "RISK_008", "RISK_015"], "k": 5, "scenario": "贷后管理"},
    {"test_id": "TOPK_013", "query": "流动性风险预测", "expected_model_ids": ["OPS_023", "OPS_025"], "k": 3, "scenario": "流动性管理"},
    {"test_id": "TOPK_014", "query": "智能客服和投诉分析", "expected_model_ids": ["OPS_020", "OPS_019", "OPS_021"], "k": 5, "scenario": "客户服务"},
    {"test_id": "TOPK_015", "query": "合规制度匹配和监管报表", "expected_model_ids": ["OPS_012", "OPS_014", "OPS_034"], "k": 5, "scenario": "合规管理"},
]

topk_path = os.path.join(EVAL_DIR, "topk_eval.jsonl")
with open(topk_path, "w", encoding="utf-8") as f:
    for item in TOP_K_EVAL:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
print(f"[B-11] Created {topk_path} with {len(TOP_K_EVAL)} test cases")

# ============================================================
# explanation_survey_mock.json - Mock explanation survey
# ============================================================
SURVEY_MOCK = {
    "survey_meta": {
        "survey_id": "SURVEY_202606",
        "title": "模型推荐解释满意度调研",
        "survey_date": "2026-06-23",
        "respondent_count": 50,
        "department_distribution": {"信贷部": 15, "零售银行部": 12, "运营管理部": 10, "合规部": 8, "科技部": 5},
        "role_distribution": {"业务主管": 18, "风控经理": 12, "产品经理": 10, "数据分析师": 6, "合规专员": 4}
    },
    "questions": [
        {"q_id": "Q1", "question": "推荐结果的解释是否清晰易懂？", "type": "likert_5", "avg_score": 4.2, "score_distribution": {"5": 22, "4": 18, "3": 7, "2": 2, "1": 1}},
        {"q_id": "Q2", "question": "推荐的模型是否满足业务需求？", "type": "likert_5", "avg_score": 4.0, "score_distribution": {"5": 15, "4": 22, "3": 8, "2": 4, "1": 1}},
        {"q_id": "Q3", "question": "推荐理由中的业务逻辑是否合理？", "type": "likert_5", "avg_score": 4.3, "score_distribution": {"5": 25, "4": 17, "3": 6, "2": 1, "1": 1}},
        {"q_id": "Q4", "question": "组合推荐方案是否具有可操作性？", "type": "likert_5", "avg_score": 3.9, "score_distribution": {"5": 12, "4": 20, "3": 12, "2": 4, "1": 2}},
        {"q_id": "Q5", "question": "与现有业务系统的对接难度如何？", "type": "likert_5", "avg_score": 3.5, "score_distribution": {"5": 8, "4": 15, "3": 18, "2": 7, "1": 2}},
        {"q_id": "Q6", "question": "您是否信任推荐结果的准确性？", "type": "likert_5", "avg_score": 4.1, "score_distribution": {"5": 18, "4": 20, "3": 8, "2": 3, "1": 1}},
        {"q_id": "Q7", "question": "推荐系统对您的工作效率是否有提升？", "type": "likert_5", "avg_score": 4.4, "score_distribution": {"5": 28, "4": 15, "3": 5, "2": 1, "1": 1}},
        {"q_id": "Q8", "question": "您是否愿意在日常工作中使用推荐系统？", "type": "likert_5", "avg_score": 4.3, "score_distribution": {"5": 24, "4": 18, "3": 6, "2": 1, "1": 1}}
    ],
    "open_ended_feedback": [
        {"respondent_id": "R_001", "role": "业务主管", "feedback": "推荐的模型比较匹配我们的业务需求，但希望能看到更多同领域模型的横向对比。"},
        {"respondent_id": "R_002", "role": "风控经理", "feedback": "反欺诈模型的推荐非常准确，但组合推荐方案还可以进一步细化实施步骤。"},
        {"respondent_id": "R_003", "role": "产品经理", "feedback": "解释中的业务逻辑很清晰，有助于向业务部门说明推荐理由。"},
        {"respondent_id": "R_004", "role": "数据分析师", "feedback": "期望能提供更多模型性能的量化对比数据，辅助选择决策。"},
        {"respondent_id": "R_005", "role": "合规专员", "feedback": "合规相关模型的推荐很专业，制度匹配逻辑符合监管要求。"},
        {"respondent_id": "R_006", "role": "业务主管", "feedback": "推荐结果总体满意，但在县域特色场景下的模型覆盖还有提升空间。"},
        {"respondent_id": "R_007", "role": "运营主管", "feedback": "网点运营类模型的推荐组合很实用，直接指导了我们的排班优化。"}
    ],
    "conclusion": {
        "overall_satisfaction": 4.1,
        "nps_score": 62,
        "strengths": ["推荐解释清晰", "业务匹配度高", "工作效率提升明显"],
        "improvements": ["增加模型横向对比", "细化组合实施方案", "丰富县域特色场景覆盖"]
    }
}

survey_path = os.path.join(EVAL_DIR, "explanation_survey_mock.json")
with open(survey_path, "w", encoding="utf-8") as f:
    json.dump(SURVEY_MOCK, f, ensure_ascii=False, indent=2)
print(f"[B-11] Created {survey_path}")

print("\n=== All eval files generated! ===")
