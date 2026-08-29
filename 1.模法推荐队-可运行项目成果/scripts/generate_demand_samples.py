#!/usr/bin/env python3
"""Generate demand_samples.jsonl, demand_model_labels.jsonl, composition_cases.jsonl, and composition_templates.json."""
import json
import os

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "samples")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge")
os.makedirs(SAMPLES_DIR, exist_ok=True)

# ============================================================
# B-08: 100+ Business Demand Samples
# ============================================================
DEMAND_SAMPLES = [
    {"demand_id": "DEMAND_001", "user_query": "我们支行在县域地区有很多农户客户，想筛选出哪些农户有可能按时还款，好做贷款审批参考。", "intent": "credit_risk_assessment", "scenario": "信贷风控-农户准入评估", "urgency": "high"},
    {"demand_id": "DEMAND_002", "user_query": "需要对申请小额贷款的客户进行欺诈风险识别，防止冒名骗贷。", "intent": "anti_fraud", "scenario": "信贷风控-反欺诈", "urgency": "high"},
    {"demand_id": "DEMAND_003", "user_query": "农户申请贷款时，系统能不能根据他们的经营情况自动算出建议额度？", "intent": "amount_calculation", "scenario": "信贷风控-额度测算", "urgency": "medium"},
    {"demand_id": "DEMAND_004", "user_query": "小微企业来申请贷款，我们需要一个快速准入评分模型来判断是否达到准入标准。", "intent": "credit_risk_assessment", "scenario": "信贷风控-小微企业准入", "urgency": "high"},
    {"demand_id": "DEMAND_005", "user_query": "我们想评估小微企业的经营稳定性，看看企业的流水是否正常，有没有经营恶化的迹象。", "intent": "business_stability_analysis", "scenario": "信贷风控-企业经营分析", "urgency": "medium"},
    {"demand_id": "DEMAND_006", "user_query": "小微企业贷款申请中，怎么识别是否存在虚假交易资料和伪造流水的欺诈行为？", "intent": "anti_fraud", "scenario": "信贷风控-小微反欺诈", "urgency": "high"},
    {"demand_id": "DEMAND_007", "user_query": "对公客户来申请贷款，需要一个自动化的信用评级模型，根据财报和经营数据给出信用等级。", "intent": "credit_rating", "scenario": "信贷风控-对公信用评级", "urgency": "high"},
    {"demand_id": "DEMAND_008", "user_query": "对公贷款发放后，希望能持续监控企业的经营异常，提前预警可能出现的风险。", "intent": "risk_monitoring", "scenario": "信贷风控-贷后预警", "urgency": "medium"},
    {"demand_id": "DEMAND_009", "user_query": "对公客户到期能否按时还贷，需要一个违约概率预测模型来评估。", "intent": "default_prediction", "scenario": "信贷风控-违约预测", "urgency": "high"},
    {"demand_id": "DEMAND_010", "user_query": "个人消费贷款审批时，我们需要一个信用评分模型来评估申请人的还款能力和信用状况。", "intent": "credit_rating", "scenario": "信贷风控-个人信用评分", "urgency": "high"},
    {"demand_id": "DEMAND_011", "user_query": "申请消费贷的客户里，有没有人是提供虚假资料或身份被盗用的？需要一个反欺诈模型筛查。", "intent": "anti_fraud", "scenario": "信贷风控-个贷反欺诈", "urgency": "high"},
    {"demand_id": "DEMAND_012", "user_query": "信用卡客户的账单逾期风险怎么预测？想提前识别可能逾期的客户进行干预。", "intent": "default_prediction", "scenario": "信贷风控-信用卡逾期预测", "urgency": "medium"},
    {"demand_id": "DEMAND_013", "user_query": "很多小微企业互相担保，形成了担保圈。怎么识别这些担保圈和其中的风险传导？", "intent": "risk_network_analysis", "scenario": "信贷风控-担保圈分析", "urgency": "medium"},
    {"demand_id": "DEMAND_014", "user_query": "集团客户旗下多个关联企业，我们需要识别它们之间的关联关系和整体风险敞口。", "intent": "risk_network_analysis", "scenario": "信贷风控-关联企业风险", "urgency": "medium"},
    {"demand_id": "DEMAND_015", "user_query": "客户贷了款之后，能不能监控他们的资金去向？发现贷款用途被挪用了要及时预警。", "intent": "risk_monitoring", "scenario": "信贷风控-资金流向监控", "urgency": "high"},
    {"demand_id": "DEMAND_016", "user_query": "多头借贷的客户风险很高，怎么识别同时在多个机构借贷的客户？", "intent": "risk_network_analysis", "scenario": "信贷风控-多头借贷识别", "urgency": "high"},
    {"demand_id": "DEMAND_017", "user_query": "存量贷款客户需要定期做风险排查，哪些客户的风险上升了需要重点关注？", "intent": "risk_monitoring", "scenario": "信贷风控-贷后排查", "urgency": "medium"},
    {"demand_id": "DEMAND_018", "user_query": "客户的违约概率PD怎么做测算？想要一个标准的PD模型用于内部评级。", "intent": "default_prediction", "scenario": "信贷风控-PD模型", "urgency": "high"},
    {"demand_id": "DEMAND_019", "user_query": "如果客户违约了，违约损失率LGD怎么算？不同担保措施下的损失率不一样。", "intent": "loss_given_default", "scenario": "信贷风控-LGD模型", "urgency": "medium"},
    {"demand_id": "DEMAND_020", "user_query": "想做基于风险定价，根据客户的风险等级给出不同的贷款利率。需要一个风险定价模型。", "intent": "risk_pricing", "scenario": "信贷风控-风险定价", "urgency": "medium"},
    {"demand_id": "DEMAND_021", "user_query": "房产抵押贷款中，抵押物的价值怎么评估和预测？特别是市场波动时抵押物减值风险。", "intent": "collateral_valuation", "scenario": "信贷风控-抵押物估值", "urgency": "medium"},
    {"demand_id": "DEMAND_022", "user_query": "贷款审批过程中，能不能自动识别申请资料里的异常信息？比如收入证明和流水不匹配。", "intent": "anomaly_detection", "scenario": "信贷风控-申请信息核验", "urgency": "high"},
    {"demand_id": "DEMAND_023", "user_query": "企业客户的资金流水异常波动怎么自动识别？有些可能涉及洗钱等非法活动。", "intent": "anomaly_detection", "scenario": "信贷风控-资金异常监测", "urgency": "high"},
    {"demand_id": "DEMAND_024", "user_query": "存量贷款客户需要做年度的风险重检，按照最新的经营和信用状况重新评级。", "intent": "credit_rating", "scenario": "信贷风控-年度重检", "urgency": "medium"},
    {"demand_id": "DEMAND_025", "user_query": "不同评级的贷款客户，它们的评级会不会随时间推移而变化？想做一个评级迁移分析。", "intent": "rating_transition", "scenario": "信贷风控-评级迁移", "urgency": "low"},
    {"demand_id": "DEMAND_026", "user_query": "整体信贷组合的风险分布是怎么样的？不同行业、区域的风险集中度需要分析。", "intent": "portfolio_risk_analysis", "scenario": "信贷风控-组合风险", "urgency": "medium"},
    {"demand_id": "DEMAND_027", "user_query": "企业客户受行业周期影响很大，能不能预测一下企业未来一段时间的经营前景？", "intent": "business_outlook_prediction", "scenario": "信贷风控-企业前景预测", "urgency": "low"},
    {"demand_id": "DEMAND_028", "user_query": "做涉农扶贫贷款，需要评估申请贷款的贫困户是否符合帮扶政策和准入要求。", "intent": "credit_risk_assessment", "scenario": "信贷风控-扶贫贷款评估", "urgency": "medium"},
    {"demand_id": "DEMAND_029", "user_query": "收回再贷的小微企业客户，能不能用他们之前的还款记录来做快速重新准入？", "intent": "credit_risk_assessment", "scenario": "信贷风控-续贷准入", "urgency": "medium"},
    {"demand_id": "DEMAND_030", "user_query": "企业客户的信用评级怎么做到行业对标？看看企业在同行业中的信用水平排名。", "intent": "credit_rating", "scenario": "信贷风控-行业对标评级", "urgency": "low"},
    {"demand_id": "DEMAND_031", "user_query": "供应链金融中，核心企业的上下游中小企业怎么评估信用风险？", "intent": "credit_risk_assessment", "scenario": "信贷风控-供应链金融", "urgency": "medium"},
    {"demand_id": "DEMAND_032", "user_query": "合同履约过程中，能不能自动识别交易对手的违约信号？比如延迟付款、频繁变更合同等。", "intent": "default_prediction", "scenario": "信贷风控-合同违约预警", "urgency": "medium"},
    {"demand_id": "DEMAND_033", "user_query": "做绿色金融贷款，需要评估企业和项目的环境风险和绿色等级。", "intent": "environmental_risk_assessment", "scenario": "信贷风控-绿色金融", "urgency": "low"},
    {"demand_id": "DEMAND_034", "user_query": "不良贷款的清收处置中，哪些客户有望通过催收收回？需要一个清收价值排序模型。", "intent": "collection_priority", "scenario": "信贷风控-催收排序", "urgency": "medium"},
    {"demand_id": "DEMAND_035", "user_query": "贷前调查阶段，如何自动核实客户提交的证明材料真实性？需要智能化的核验工具。", "intent": "anti_fraud", "scenario": "信贷风控-贷前核验", "urgency": "high"},
    # === 客户营销需求 ===
    {"demand_id": "DEMAND_036", "user_query": "县域新开卡的客户，怎么识别哪些人有贷款需求？想筛选出高转化潜力的新客做营销。", "intent": "marketing_targeting", "scenario": "客户营销-新客转化", "urgency": "high"},
    {"demand_id": "DEMAND_037", "user_query": "新开卡的客户里面，哪些人最近可能需要贷款？需要识别他们的贷款意向。", "intent": "intent_recognition", "scenario": "客户营销-意向识别", "urgency": "high"},
    {"demand_id": "DEMAND_038", "user_query": "存量客户中，哪些人可能对我们的其他产品感兴趣？想推荐存款、理财或贷款等产品。", "intent": "cross_selling", "scenario": "客户营销-交叉销售", "urgency": "high"},
    {"demand_id": "DEMAND_039", "user_query": "怎么分析客户的个人偏好？比如喜欢存款还是理财，偏好线上还是线下渠道。", "intent": "preference_analysis", "scenario": "客户营销-偏好分析", "urgency": "medium"},
    {"demand_id": "DEMAND_040", "user_query": "营销活动发出去之前，怎么知道哪些客户最可能响应？想筛选高响应客群。", "intent": "response_prediction", "scenario": "客户营销-响应预测", "urgency": "high"},
    {"demand_id": "DEMAND_041", "user_query": "不同渠道的营销效果不一样，怎么给不同客户选择最优的触达渠道？", "intent": "channel_optimization", "scenario": "客户营销-渠道优化", "urgency": "medium"},
    {"demand_id": "DEMAND_042", "user_query": "我们的客户里哪些是高价值客户？怎么识别和分层？需要对所有客户做个价值评估。", "intent": "value_assessment", "scenario": "客户营销-价值评估", "urgency": "high"},
    {"demand_id": "DEMAND_043", "user_query": "很多长时间没有交易的沉睡客户，怎么把他们重新激活？筛选最可能唤醒的客户。", "intent": "customer_reactivation", "scenario": "客户营销-沉睡唤醒", "urgency": "medium"},
    {"demand_id": "DEMAND_044", "user_query": "最近客户流失的比较多，能不能提前预测哪些客户可能要流失，好做保留措施？", "intent": "churn_prediction", "scenario": "客户营销-流失预警", "urgency": "high"},
    {"demand_id": "DEMAND_045", "user_query": "客户从新客到成熟再到流失，怎么识别每个客户处在生命周期的哪个阶段？", "intent": "lifecycle_management", "scenario": "客户营销-生命周期", "urgency": "medium"},
    {"demand_id": "DEMAND_046", "user_query": "农户客户的理财需求怎么挖掘？他们除了存款之外还可以推荐什么产品？", "intent": "preference_analysis", "scenario": "客户营销-农户理财", "urgency": "medium"},
    {"demand_id": "DEMAND_047", "user_query": "小微企业客户有没有贷款以外的金融需求？比如代发工资、收款码等产品。", "intent": "cross_selling", "scenario": "客户营销-小微综合营销", "urgency": "medium"},
    {"demand_id": "DEMAND_048", "user_query": "对公客户的价值贡献怎么评估？不同企业的存款、贷款、中间业务收入需要综合分析。", "intent": "value_assessment", "scenario": "客户营销-对公价值评估", "urgency": "medium"},
    {"demand_id": "DEMAND_049", "user_query": "代发工资客户的资金留存率怎么提升？识别哪些代发客户有理财需求。", "intent": "conversion_prediction", "scenario": "客户营销-代发客群经营", "urgency": "medium"},
    {"demand_id": "DEMAND_050", "user_query": "手机银行APP的活跃度怎么提升？哪些客户最可能被促活？", "intent": "customer_reactivation", "scenario": "客户营销-APP促活", "urgency": "high"},
    {"demand_id": "DEMAND_051", "user_query": "信用卡新户怎么促首刷？哪些客户开卡后最可能激活使用？", "intent": "conversion_prediction", "scenario": "客户营销-信用卡首刷", "urgency": "high"},
    {"demand_id": "DEMAND_052", "user_query": "理财产品的推荐怎么做？根据客户的风险偏好和资产情况推荐合适的理财产品。", "intent": "preference_analysis", "scenario": "客户营销-理财推荐", "urgency": "high"},
    {"demand_id": "DEMAND_053", "user_query": "存款流失的客户有什么特征？怎么能提前发现可能转走存款的客户？", "intent": "churn_prediction", "scenario": "客户营销-存款流失", "urgency": "medium"},
    {"demand_id": "DEMAND_054", "user_query": "怎么计算一个客户在银行的综合价值？包括当前贡献和未来潜力。", "intent": "value_assessment", "scenario": "客户营销-客户价值", "urgency": "medium"},
    {"demand_id": "DEMAND_055", "user_query": "不同客户喜欢什么营销渠道？短信、电话、微信还是APP推送？需要做渠道偏好分析。", "intent": "channel_optimization", "scenario": "客户营销-渠道偏好", "urgency": "medium"},
    {"demand_id": "DEMAND_056", "user_query": "营销活动什么时间触达客户效果最好？需要找到每个客户的最佳触达时机。", "intent": "channel_optimization", "scenario": "客户营销-触达时机", "urgency": "low"},
    {"demand_id": "DEMAND_057", "user_query": "营销触达的频次多少合适？太频繁客户反感，太少又没效果。", "intent": "channel_optimization", "scenario": "客户营销-频次优化", "urgency": "low"},
    {"demand_id": "DEMAND_058", "user_query": "校园场景的年轻客群有什么金融需求？怎么针对大学生做精准营销？", "intent": "segmentation", "scenario": "客户营销-年轻客群", "urgency": "medium"},
    {"demand_id": "DEMAND_059", "user_query": "扫码收单商户怎么拓展？哪些商户最有可能签约使用我们的收款码？", "intent": "conversion_prediction", "scenario": "客户营销-商户拓展", "urgency": "medium"},
    {"demand_id": "DEMAND_060", "user_query": "首次贷款的客户体验怎么做才能更好？怎么给首贷客户推荐最合适的产品？", "intent": "preference_analysis", "scenario": "客户营销-首贷体验", "urgency": "medium"},
    {"demand_id": "DEMAND_061", "user_query": "普惠金融客户群体怎么匹配最适合他们的产品和服务？", "intent": "segmentation", "scenario": "客户营销-普惠匹配", "urgency": "medium"},
    {"demand_id": "DEMAND_062", "user_query": "不同地区的客户消费习惯不同，怎么做区域化的精准营销策略？", "intent": "segmentation", "scenario": "客户营销-区域营销", "urgency": "medium"},
    {"demand_id": "DEMAND_063", "user_query": "怎么对客户做全生命周期的营销规划？从获客到挽留各阶段用什么策略？", "intent": "lifecycle_management", "scenario": "客户营销-全周期营销", "urgency": "medium"},
    {"demand_id": "DEMAND_064", "user_query": "客户在银行持有的产品数量比较少，怎么找出最有交叉销售潜力的客户？", "intent": "cross_selling", "scenario": "客户营销-交叉潜力", "urgency": "high"},
    {"demand_id": "DEMAND_065", "user_query": "有没有办法把客户分成不同的群体，每个群体用不同的营销策略？", "intent": "segmentation", "scenario": "客户营销-客群分层", "urgency": "high"},
    {"demand_id": "DEMAND_066", "user_query": "企业客户的上下游供应链中有哪些金融营销机会？比如给供应商提供应收账款融资。", "intent": "cross_selling", "scenario": "客户营销-供应链营销", "urgency": "low"},
    {"demand_id": "DEMAND_067", "user_query": "农民的种植养殖数据能不能用来评估他们的经营情况和金融需求？", "intent": "alternative_data_scoring", "scenario": "客户营销-三农数据应用", "urgency": "medium"},
    {"demand_id": "DEMAND_068", "user_query": "种粮大户的收成预测能不能用来做贷款评估的依据？", "intent": "alternative_data_scoring", "scenario": "客户营销-农业经营评估", "urgency": "low"},
    {"demand_id": "DEMAND_069", "user_query": "农户的经营周转资金需求季节性很强，怎么判断他们的资金需求高峰期？", "intent": "demand_forecasting_customer", "scenario": "客户营销-资金需求预测", "urgency": "low"},
    {"demand_id": "DEMAND_070", "user_query": "客户即将有资金到期（比如定期存款到期、理财到期），怎么提前做好营销承接？", "intent": "event_triggered_marketing", "scenario": "客户营销-事件营销", "urgency": "medium"},
    # === 运营管理需求 ===
    {"demand_id": "DEMAND_071", "user_query": "银行网点每天的客流量波动很大，能不能预测每天的客流方便我们排班？", "intent": "workforce_management", "scenario": "运营管理-客流预测", "urgency": "high"},
    {"demand_id": "DEMAND_072", "user_query": "柜员排班总是人手不够或过剩，有没有智能排班的方案？", "intent": "workforce_management", "scenario": "运营管理-智能排班", "urgency": "high"},
    {"demand_id": "DEMAND_073", "user_query": "网点的各项业务量怎么预测？好提前安排窗口和资源。", "intent": "workforce_management", "scenario": "运营管理-业务量预测", "urgency": "medium"},
    {"demand_id": "DEMAND_074", "user_query": "我们的网点布在哪里最合适？新设或迁址需要数据支撑决策。", "intent": "branch_planning", "scenario": "运营管理-网点布局", "urgency": "medium"},
    {"demand_id": "DEMAND_075", "user_query": "怎么评价每个网点的综合运营效率？从效益、服务、运营多个维度打分排名。", "intent": "performance_evaluation", "scenario": "运营管理-效能评价", "urgency": "medium"},
    {"demand_id": "DEMAND_076", "user_query": "很多柜面业务其实可以在智能柜员机或手机上办，怎么引导客户分流？", "intent": "process_optimization", "scenario": "运营管理-业务分流", "urgency": "medium"},
    {"demand_id": "DEMAND_077", "user_query": "网点厅堂的客户动线怎么设计才能提升体验和营销转化率？", "intent": "branch_planning", "scenario": "运营管理-动线设计", "urgency": "low"},
    {"demand_id": "DEMAND_078", "user_query": "ATM和智能柜员机老是出故障，能不能提前预测故障提前维护？", "intent": "it_operations", "scenario": "运营管理-设备运维", "urgency": "high"},
    {"demand_id": "DEMAND_079", "user_query": "银行的交易流水里，哪些可能是洗钱行为？需要自动识别可疑交易。", "intent": "aml_compliance", "scenario": "运营管理-反洗钱", "urgency": "high"},
    {"demand_id": "DEMAND_080", "user_query": "按照反洗钱要求，需要给所有客户做洗钱风险评级，这个能自动化吗？", "intent": "aml_compliance", "scenario": "运营管理-洗钱评级", "urgency": "high"},
    {"demand_id": "DEMAND_081", "user_query": "多个账户之间频繁转账，看起来像洗钱团伙，怎么挖掘出这种团伙关系？", "intent": "aml_compliance", "scenario": "运营管理-团伙挖掘", "urgency": "medium"},
    {"demand_id": "DEMAND_082", "user_query": "业务操作是否符合合规制度要求？想做一个智能合规检查工具。", "intent": "compliance_management", "scenario": "运营管理-合规检查", "urgency": "medium"},
    {"demand_id": "DEMAND_083", "user_query": "柜员和客户经理的操作行为有没有异常？能不能自动监测和预警？", "intent": "risk_monitoring", "scenario": "运营管理-员工行为监测", "urgency": "high"},
    {"demand_id": "DEMAND_084", "user_query": "银保监会和央行的监管报表每月都要报，能不能自动从系统取数生成？", "intent": "compliance_management", "scenario": "运营管理-监管报表", "urgency": "high"},
    {"demand_id": "DEMAND_085", "user_query": "客户在手机银行和网银上的交易，怎么实时识别和拦截欺诈交易？", "intent": "anti_fraud", "scenario": "运营管理-交易反欺诈", "urgency": "high"},
    {"demand_id": "DEMAND_086", "user_query": "贷款审批任务能不能根据复杂度和人员专长自动分配？提高审批效率。", "intent": "workflow_optimization", "scenario": "运营管理-审批分配", "urgency": "medium"},
    {"demand_id": "DEMAND_087", "user_query": "开户流程太长了，能不能评估哪些环节可以简化或合并？", "intent": "process_optimization", "scenario": "运营管理-流程简化", "urgency": "medium"},
    {"demand_id": "DEMAND_088", "user_query": "柜面哪些业务需要授权？有些授权太频繁能不能优化规则？", "intent": "process_optimization", "scenario": "运营管理-授权优化", "urgency": "low"},
    {"demand_id": "DEMAND_089", "user_query": "客户投诉越来越多，能不能自动分类和分析投诉的根因？", "intent": "customer_service", "scenario": "运营管理-投诉分析", "urgency": "medium"},
    {"demand_id": "DEMAND_090", "user_query": "想做一个智能客服，客户提问后自动匹配FAQ给出答案。", "intent": "customer_service", "scenario": "运营管理-智能客服", "urgency": "high"},
    {"demand_id": "DEMAND_091", "user_query": "IT运维工单、业务工单怎么自动分配给最合适的人处理？", "intent": "workflow_optimization", "scenario": "运营管理-工单分配", "urgency": "medium"},
    {"demand_id": "DEMAND_092", "user_query": "银行的业务流程有没有瓶颈和效率低下的环节？想做一个流程挖掘分析。", "intent": "process_optimization", "scenario": "运营管理-流程挖掘", "urgency": "low"},
    {"demand_id": "DEMAND_093", "user_query": "银行短期流动性缺口怎么提前预测？防止出现流动性风险。", "intent": "treasury_management", "scenario": "运营管理-流动性预测", "urgency": "high"},
    {"demand_id": "DEMAND_094", "user_query": "贷款利率怎么定才合理？要覆盖风险成本又有市场竞争力。", "intent": "risk_pricing", "scenario": "运营管理-利率定价", "urgency": "medium"},
    {"demand_id": "DEMAND_095", "user_query": "贷款和存款的期限结构怎么配比最好？想做资产负债结构优化。", "intent": "treasury_management", "scenario": "运营管理-资产负债优化", "urgency": "medium"},
    {"demand_id": "DEMAND_096", "user_query": "下个季度的费用预算怎么编制？需要根据业务量预测做预算。", "intent": "financial_management", "scenario": "运营管理-预算预测", "urgency": "medium"},
    {"demand_id": "DEMAND_097", "user_query": "收单商户的交易有没有套现或虚假交易的风险？需要持续监测。", "intent": "risk_monitoring", "scenario": "运营管理-商户风险", "urgency": "high"},
    {"demand_id": "DEMAND_098", "user_query": "手机银行、柜面、客服等各渠道的服务质量怎么评估排名？", "intent": "performance_evaluation", "scenario": "运营管理-渠道质量", "urgency": "medium"},
    {"demand_id": "DEMAND_099", "user_query": "客户经理的季度绩效能不能提前预测？好针对性地做辅导。", "intent": "workforce_management", "scenario": "运营管理-绩效预测", "urgency": "medium"},
    {"demand_id": "DEMAND_100", "user_query": "员工的培训需求怎么识别？不同岗位的员工需要什么培训？", "intent": "workforce_management", "scenario": "运营管理-培训需求", "urgency": "low"},
    {"demand_id": "DEMAND_101", "user_query": "明年各岗位需要多少人？能不能根据业务量预测做人力资源规划？", "intent": "workforce_management", "scenario": "运营管理-人力规划", "urgency": "medium"},
    {"demand_id": "DEMAND_102", "user_query": "核心岗位的员工会不会离职？怎么提前预警关键人才流失风险？", "intent": "workforce_management", "scenario": "运营管理-离职预警", "urgency": "medium"},
    {"demand_id": "DEMAND_103", "user_query": "每月的经营分析报告能不能自动生成？从数据提取到报告撰写全流程自动化。", "intent": "report_automation", "scenario": "运营管理-报告自动化", "urgency": "medium"},
    {"demand_id": "DEMAND_104", "user_query": "业务系统的数据质量怎么监控？经常有数据不准、缺失的问题。", "intent": "data_governance", "scenario": "运营管理-数据质量", "urgency": "high"},
    {"demand_id": "DEMAND_105", "user_query": "运营成本一直在涨，哪些环节成本高？怎么优化运营成本？", "intent": "financial_management", "scenario": "运营管理-成本优化", "urgency": "medium"},
]

# ============================================================
# B-08: Write demand_samples.jsonl
# ============================================================
demand_path = os.path.join(SAMPLES_DIR, "demand_samples.jsonl")
with open(demand_path, "w", encoding="utf-8") as f:
    for d in DEMAND_SAMPLES:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print(f"[B-08] Created {demand_path} with {len(DEMAND_SAMPLES)} demand samples")

# ============================================================
# B-09: Generate demand_model_labels.jsonl (105 demand-model annotations)
# ============================================================
# Load all model IDs
model_ids = []
for prefix in ["RISK", "MKT", "OPS"]:
    for i in range(1, 36):
        model_ids.append(f"{prefix}_{i:03d}")

LABELS = [
    # DEMAND_001-010 -> RISK models
    {"demand_id": "DEMAND_001", "model_id": "RISK_001", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "农户准入评分模型直接匹配"},
    {"demand_id": "DEMAND_001", "model_id": "RISK_004", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_1", "note": "小微企业准入作为替代参考"},
    {"demand_id": "DEMAND_002", "model_id": "RISK_002", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_1", "note": "农户小额贷款反欺诈模型"},
    {"demand_id": "DEMAND_002", "model_id": "OPS_015", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_1", "note": "交易反欺诈可部分适用"},
    {"demand_id": "DEMAND_003", "model_id": "RISK_003", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_1", "note": "农户小额贷款额度测算模型"},
    {"demand_id": "DEMAND_004", "model_id": "RISK_004", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_1", "note": "小微企业贷前准入模型"},
    {"demand_id": "DEMAND_005", "model_id": "RISK_005", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_1", "note": "小微企业经营稳定性分析模型"},
    {"demand_id": "DEMAND_006", "model_id": "RISK_006", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "小微企业反欺诈模型"},
    {"demand_id": "DEMAND_007", "model_id": "RISK_007", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_1", "note": "对公客户信用评级模型"},
    {"demand_id": "DEMAND_008", "model_id": "RISK_008", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_1", "note": "对公贷款贷后风险预警模型"},
    {"demand_id": "DEMAND_009", "model_id": "RISK_009", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_1", "note": "对公贷款违约预测模型"},
    {"demand_id": "DEMAND_010", "model_id": "RISK_010", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "个人消费贷信用评分模型"},
    # DEMAND_011-020 -> RISK models
    {"demand_id": "DEMAND_011", "model_id": "RISK_011", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_1", "note": "个人贷款欺诈识别模型"},
    {"demand_id": "DEMAND_012", "model_id": "RISK_012", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "信用卡逾期风险评分模型"},
    {"demand_id": "DEMAND_013", "model_id": "RISK_013", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_1", "note": "担保圈风险识别模型"},
    {"demand_id": "DEMAND_014", "model_id": "RISK_014", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_1", "note": "关联企业风险识别模型"},
    {"demand_id": "DEMAND_015", "model_id": "RISK_015", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_1", "note": "贷款用途异常识别模型"},
    {"demand_id": "DEMAND_016", "model_id": "RISK_016", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "多头借贷风险识别模型"},
    {"demand_id": "DEMAND_017", "model_id": "RISK_017", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_1", "note": "贷后风险排查模型"},
    {"demand_id": "DEMAND_018", "model_id": "RISK_018", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_1", "note": "违约概率PD预测模型"},
    {"demand_id": "DEMAND_019", "model_id": "RISK_019", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_1", "note": "违约损失率LGD测算模型"},
    {"demand_id": "DEMAND_020", "model_id": "RISK_020", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_1", "note": "风险定价模型"},
    # DEMAND_021-035 -> RISK models
    {"demand_id": "DEMAND_021", "model_id": "RISK_021", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_1", "note": "抵押物价值预测模型"},
    {"demand_id": "DEMAND_022", "model_id": "RISK_022", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_2", "note": "贷款申请异常检测模型"},
    {"demand_id": "DEMAND_023", "model_id": "RISK_023", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_2", "note": "客户资金异常检测模型"},
    {"demand_id": "DEMAND_024", "model_id": "RISK_024", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_2", "note": "存量客户风险重检模型"},
    {"demand_id": "DEMAND_025", "model_id": "RISK_025", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_2", "note": "评级迁移预测模型"},
    {"demand_id": "DEMAND_026", "model_id": "RISK_026", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_2", "note": "客户风险分布模型"},
    {"demand_id": "DEMAND_027", "model_id": "RISK_027", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_2", "note": "授信客户风险重检模型"},
    {"demand_id": "DEMAND_028", "model_id": "RISK_028", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_2", "note": "企业风险预警模型"},
    {"demand_id": "DEMAND_029", "model_id": "RISK_029", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_2", "note": "贷款催收预测模型"},
    {"demand_id": "DEMAND_030", "model_id": "RISK_030", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_2", "note": "涉农产业信贷评估模型"},
    {"demand_id": "DEMAND_031", "model_id": "RISK_031", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_2", "note": "收回再贷准入模型"},
    {"demand_id": "DEMAND_032", "model_id": "RISK_032", "relevance_score": 0.89, "label_type": "primary", "annotator": "expert_2", "note": "企业信用风险评级模型"},
    {"demand_id": "DEMAND_033", "model_id": "RISK_033", "relevance_score": 0.85, "label_type": "primary", "annotator": "expert_2", "note": "合同对手风险识别模型"},
    {"demand_id": "DEMAND_034", "model_id": "RISK_034", "relevance_score": 0.88, "label_type": "primary", "annotator": "expert_2", "note": "不良资产定价模型"},
    {"demand_id": "DEMAND_035", "model_id": "RISK_035", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_2", "note": "贷前反欺诈真实性识别模型"},
    # DEMAND_036-070 -> MKT models
    {"demand_id": "DEMAND_036", "model_id": "MKT_001", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_3", "note": "县域新客首贷转化预测模型"},
    {"demand_id": "DEMAND_037", "model_id": "MKT_002", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_3", "note": "新客贷款意向识别模型"},
    {"demand_id": "DEMAND_038", "model_id": "MKT_003", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_3", "note": "存量客户交叉销售模型"},
    {"demand_id": "DEMAND_039", "model_id": "MKT_004", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_3", "note": "客户产品偏好模型"},
    {"demand_id": "DEMAND_040", "model_id": "MKT_005", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_3", "note": "客户响应率预测模型"},
    {"demand_id": "DEMAND_041", "model_id": "MKT_006", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_3", "note": "营销渠道优化模型"},
    {"demand_id": "DEMAND_042", "model_id": "MKT_007", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_3", "note": "高价值客户识别模型"},
    {"demand_id": "DEMAND_043", "model_id": "MKT_008", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_3", "note": "沉睡客户唤醒模型"},
    {"demand_id": "DEMAND_044", "model_id": "MKT_009", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_3", "note": "客户流失预测模型"},
    {"demand_id": "DEMAND_045", "model_id": "MKT_010", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_3", "note": "客户生命周期阶段识别模型"},
    {"demand_id": "DEMAND_046", "model_id": "MKT_011", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_3", "note": "农户理财需求预测模型"},
    {"demand_id": "DEMAND_047", "model_id": "MKT_012", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_3", "note": "小微企业综合需求预测模型"},
    {"demand_id": "DEMAND_048", "model_id": "MKT_013", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_3", "note": "对公客户综合贡献度模型"},
    {"demand_id": "DEMAND_049", "model_id": "MKT_014", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_3", "note": "代发客户转化模型"},
    {"demand_id": "DEMAND_050", "model_id": "MKT_015", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_3", "note": "手机银行活跃促活模型"},
    {"demand_id": "DEMAND_051", "model_id": "MKT_016", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_3", "note": "信用卡营销模型"},
    {"demand_id": "DEMAND_052", "model_id": "MKT_017", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_3", "note": "理财产品偏好模型"},
    {"demand_id": "DEMAND_053", "model_id": "MKT_018", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_3", "note": "存款流失预测模型"},
    {"demand_id": "DEMAND_054", "model_id": "MKT_019", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_3", "note": "客户价值潜力模型"},
    {"demand_id": "DEMAND_055", "model_id": "MKT_020", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_4", "note": "客户渠道偏好模型"},
    {"demand_id": "DEMAND_056", "model_id": "MKT_021", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_4", "note": "营销最佳时机模型"},
    {"demand_id": "DEMAND_057", "model_id": "MKT_022", "relevance_score": 0.89, "label_type": "primary", "annotator": "expert_4", "note": "营销频次优化模型"},
    {"demand_id": "DEMAND_058", "model_id": "MKT_023", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_4", "note": "客群客户价值识别模型"},
    {"demand_id": "DEMAND_059", "model_id": "MKT_024", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_4", "note": "扫码商户拓展模型"},
    {"demand_id": "DEMAND_060", "model_id": "MKT_025", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_4", "note": "首贷客户产品推荐模型"},
    {"demand_id": "DEMAND_061", "model_id": "MKT_026", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_4", "note": "普惠客户产品匹配模型"},
    {"demand_id": "DEMAND_062", "model_id": "MKT_027", "relevance_score": 0.88, "label_type": "primary", "annotator": "expert_4", "note": "区域化营销模型"},
    {"demand_id": "DEMAND_063", "model_id": "MKT_010", "relevance_score": 0.85, "label_type": "alternative", "annotator": "expert_4", "note": "生命周期阶段识别可作为基础"},
    {"demand_id": "DEMAND_064", "model_id": "MKT_003", "relevance_score": 0.90, "label_type": "alternative", "annotator": "expert_4", "note": "交叉销售模型可覆盖"},
    {"demand_id": "DEMAND_065", "model_id": "MKT_004", "relevance_score": 0.87, "label_type": "alternative", "annotator": "expert_4", "note": "偏好模型可辅助分群"},
    {"demand_id": "DEMAND_066", "model_id": "MKT_028", "relevance_score": 0.86, "label_type": "primary", "annotator": "expert_4", "note": "客户资产配置模型"},
    {"demand_id": "DEMAND_067", "model_id": "MKT_029", "relevance_score": 0.85, "label_type": "primary", "annotator": "expert_4", "note": "多产品协同推荐模型"},
    {"demand_id": "DEMAND_068", "model_id": "MKT_030", "relevance_score": 0.84, "label_type": "primary", "annotator": "expert_4", "note": "客户经营策略推荐模型"},
    {"demand_id": "DEMAND_069", "model_id": "MKT_031", "relevance_score": 0.83, "label_type": "primary", "annotator": "expert_4", "note": "企业客户转化模型"},
    {"demand_id": "DEMAND_070", "model_id": "MKT_032", "relevance_score": 0.87, "label_type": "primary", "annotator": "expert_4", "note": "农村电商客群识别模型"},
    # Additional MKT annotations
    {"demand_id": "DEMAND_036", "model_id": "MKT_002", "relevance_score": 0.70, "label_type": "alternative", "annotator": "expert_3", "note": "意向识别可辅助"},
    {"demand_id": "DEMAND_038", "model_id": "MKT_004", "relevance_score": 0.65, "label_type": "alternative", "annotator": "expert_3", "note": "偏好分析可辅助"},
    {"demand_id": "DEMAND_040", "model_id": "MKT_004", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_3", "note": "偏好数据可辅助响应预测"},
    {"demand_id": "DEMAND_044", "model_id": "MKT_008", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_3", "note": "沉睡唤醒可辅助流失预防"},
    # DEMAND_071-105 -> OPS models
    {"demand_id": "DEMAND_071", "model_id": "OPS_001", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_5", "note": "网点客流预测模型"},
    {"demand_id": "DEMAND_072", "model_id": "OPS_002", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_5", "note": "智能排班优化模型"},
    {"demand_id": "DEMAND_073", "model_id": "OPS_003", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_5", "note": "网点业务量预测模型"},
    {"demand_id": "DEMAND_074", "model_id": "OPS_004", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_5", "note": "网点布局评估模型"},
    {"demand_id": "DEMAND_075", "model_id": "OPS_005", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_5", "note": "网点效能评价模型"},
    {"demand_id": "DEMAND_076", "model_id": "OPS_006", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_5", "note": "柜面业务分流模型"},
    {"demand_id": "DEMAND_077", "model_id": "OPS_007", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_5", "note": "网点动线优化模型"},
    {"demand_id": "DEMAND_078", "model_id": "OPS_008", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_5", "note": "网点设备运维预测模型"},
    {"demand_id": "DEMAND_079", "model_id": "OPS_009", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_5", "note": "反洗钱可疑交易识别模型"},
    {"demand_id": "DEMAND_080", "model_id": "OPS_010", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_5", "note": "客户洗钱风险评级模型"},
    {"demand_id": "DEMAND_081", "model_id": "OPS_011", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_5", "note": "反洗钱团伙挖掘模型"},
    {"demand_id": "DEMAND_082", "model_id": "OPS_012", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_5", "note": "合规制度智能匹配模型"},
    {"demand_id": "DEMAND_083", "model_id": "OPS_013", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_5", "note": "员工操作风险监测模型"},
    {"demand_id": "DEMAND_084", "model_id": "OPS_014", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_5", "note": "监管报表自动生成模型"},
    {"demand_id": "DEMAND_085", "model_id": "OPS_015", "relevance_score": 0.97, "label_type": "primary", "annotator": "expert_5", "note": "反欺诈交易实时拦截模型"},
    {"demand_id": "DEMAND_086", "model_id": "OPS_016", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_5", "note": "贷款审批流程优化模型"},
    {"demand_id": "DEMAND_087", "model_id": "OPS_017", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_5", "note": "开户流程简化评估模型"},
    {"demand_id": "DEMAND_088", "model_id": "OPS_018", "relevance_score": 0.90, "label_type": "primary", "annotator": "expert_5", "note": "柜面业务授权优化模型"},
    {"demand_id": "DEMAND_089", "model_id": "OPS_019", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_5", "note": "客户投诉分析模型"},
    {"demand_id": "DEMAND_090", "model_id": "OPS_020", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_5", "note": "智能客服问答匹配模型"},
    {"demand_id": "DEMAND_091", "model_id": "OPS_021", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_6", "note": "智能工单分配模型"},
    {"demand_id": "DEMAND_092", "model_id": "OPS_022", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_6", "note": "业务流程时序挖掘模型"},
    {"demand_id": "DEMAND_093", "model_id": "OPS_023", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_6", "note": "流动性风险预测模型"},
    {"demand_id": "DEMAND_094", "model_id": "OPS_024", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_6", "note": "利率定价评估模型"},
    {"demand_id": "DEMAND_095", "model_id": "OPS_025", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_6", "note": "资产负债配置优化模型"},
    {"demand_id": "DEMAND_096", "model_id": "OPS_026", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_6", "note": "费用预算预测模型"},
    {"demand_id": "DEMAND_097", "model_id": "OPS_027", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_6", "note": "收单商户风险监测模型"},
    {"demand_id": "DEMAND_098", "model_id": "OPS_028", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_6", "note": "渠道服务质量评估模型"},
    {"demand_id": "DEMAND_099", "model_id": "OPS_029", "relevance_score": 0.92, "label_type": "primary", "annotator": "expert_6", "note": "客户经理绩效预测模型"},
    {"demand_id": "DEMAND_100", "model_id": "OPS_030", "relevance_score": 0.91, "label_type": "primary", "annotator": "expert_6", "note": "员工培训需求分析模型"},
    {"demand_id": "DEMAND_101", "model_id": "OPS_031", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_6", "note": "人力资源供需预测模型"},
    {"demand_id": "DEMAND_102", "model_id": "OPS_032", "relevance_score": 0.94, "label_type": "primary", "annotator": "expert_6", "note": "员工异动风险预警模型"},
    {"demand_id": "DEMAND_103", "model_id": "OPS_033", "relevance_score": 0.95, "label_type": "primary", "annotator": "expert_6", "note": "经营分析报告自动生成模型"},
    {"demand_id": "DEMAND_104", "model_id": "OPS_034", "relevance_score": 0.96, "label_type": "primary", "annotator": "expert_6", "note": "数据质量监控模型"},
    {"demand_id": "DEMAND_105", "model_id": "OPS_035", "relevance_score": 0.93, "label_type": "primary", "annotator": "expert_6", "note": "运营成本分析优化模型"},
    # Additional alternative labels
    {"demand_id": "DEMAND_071", "model_id": "OPS_003", "relevance_score": 0.65, "label_type": "alternative", "annotator": "expert_5", "note": "业务量预测辅助客流预测"},
    {"demand_id": "DEMAND_079", "model_id": "OPS_015", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_5", "note": "交易反欺诈模型可辅助可疑交易识别"},
    {"demand_id": "DEMAND_085", "model_id": "OPS_009", "relevance_score": 0.50, "label_type": "alternative", "annotator": "expert_5", "note": "反洗钱模型有部分重叠"},
    {"demand_id": "DEMAND_090", "model_id": "OPS_019", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_5", "note": "投诉分析可辅助FAQ优化"},
    {"demand_id": "DEMAND_093", "model_id": "OPS_025", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_6", "note": "资产负债优化可辅助流动性管理"},
    {"demand_id": "DEMAND_001", "model_id": "RISK_030", "relevance_score": 0.50, "label_type": "alternative", "annotator": "expert_1", "note": "涉农模型可作为扩展参考"},
    {"demand_id": "DEMAND_036", "model_id": "MKT_005", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_3", "note": "响应率预测可辅助转化预测"},
    {"demand_id": "DEMAND_050", "model_id": "MKT_008", "relevance_score": 0.58, "label_type": "alternative", "annotator": "expert_3", "note": "沉睡唤醒与促活有交叉"},
    {"demand_id": "DEMAND_067", "model_id": "MKT_033", "relevance_score": 0.88, "label_type": "primary", "annotator": "expert_4", "note": "粮食种植面积产量预测模型"},
    {"demand_id": "DEMAND_068", "model_id": "MKT_034", "relevance_score": 0.89, "label_type": "primary", "annotator": "expert_4", "note": "农业生产经营景气指数模型"},
    {"demand_id": "DEMAND_069", "model_id": "MKT_035", "relevance_score": 0.85, "label_type": "primary", "annotator": "expert_4", "note": "客户活动意愿预测模型"},
    {"demand_id": "DEMAND_010", "model_id": "RISK_011", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_1", "note": "反欺诈可辅助信用评分"},
    {"demand_id": "DEMAND_018", "model_id": "RISK_020", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_1", "note": "风险定价与PD模型可配合使用"},
    {"demand_id": "DEMAND_031", "model_id": "RISK_007", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_2", "note": "企业信用评级可辅助供应链金融"},
    {"demand_id": "DEMAND_038", "model_id": "MKT_007", "relevance_score": 0.55, "label_type": "alternative", "annotator": "expert_3", "note": "高价值识别可辅助交叉销售"},
    {"demand_id": "DEMAND_044", "model_id": "MKT_018", "relevance_score": 0.60, "label_type": "alternative", "annotator": "expert_3", "note": "存款流失与客户流失有相关性"},
]

label_path = os.path.join(SAMPLES_DIR, "demand_model_labels.jsonl")
with open(label_path, "w", encoding="utf-8") as f:
    for lbl in LABELS:
        f.write(json.dumps(lbl, ensure_ascii=False) + "\n")
print(f"[B-09] Created {label_path} with {len(LABELS)} labels")

# ============================================================
# B-10: Generate composition_cases.jsonl (30+ cases)
# ============================================================
COMPOSITION_CASES = [
    {"case_id": "COMP_001", "name": "农户贷款全流程智能审批", "description": "从农户申请到放款的完整流程，包括准入评分、反欺诈、额度测算、利率定价。", "models": ["RISK_001", "RISK_002", "RISK_003", "OPS_024"], "demand_ids": ["DEMAND_001", "DEMAND_002", "DEMAND_003", "DEMAND_094"], "scenario": "信贷风控-农户贷款", "complexity": "high", "estimated_impact": "审批效率提升70%，不良率控制在1.5%以内"},
    {"case_id": "COMP_002", "name": "小微企业综合信贷服务", "description": "小微企业贷款全链路，包含准入、经营稳定性评估、反欺诈和违约预测。", "models": ["RISK_004", "RISK_005", "RISK_006", "RISK_009"], "demand_ids": ["DEMAND_004", "DEMAND_005", "DEMAND_006", "DEMAND_009"], "scenario": "信贷风控-小微企业", "complexity": "high", "estimated_impact": "小微贷款审批效率提升50%，不良率降低0.8%"},
    {"case_id": "COMP_003", "name": "对公客户全周期风险管理", "description": "对公客户的信用评级、贷后预警、违约预测全流程风险管理。", "models": ["RISK_007", "RISK_008", "RISK_009", "RISK_014"], "demand_ids": ["DEMAND_007", "DEMAND_008", "DEMAND_009", "DEMAND_014"], "scenario": "信贷风控-对公客户", "complexity": "high", "estimated_impact": "对公风险预警提前45天，风险损失降低25%"},
    {"case_id": "COMP_004", "name": "个人消费贷智能审批", "description": "个人消费贷款的信用评分、反欺诈和申请信息异常核验组合。", "models": ["RISK_010", "RISK_011", "RISK_022"], "demand_ids": ["DEMAND_010", "DEMAND_011", "DEMAND_022"], "scenario": "信贷风控-个人消费贷", "complexity": "medium", "estimated_impact": "审批自动化率提升至65%，欺诈损失降低40%"},
    {"case_id": "COMP_005", "name": "信用卡风险全流程管理", "description": "信用卡申请、使用、逾期全流程的风险识别和预警。", "models": ["RISK_012", "RISK_016", "RISK_023", "OPS_015"], "demand_ids": ["DEMAND_012", "DEMAND_016", "DEMAND_023", "DEMAND_085"], "scenario": "信贷风控-信用卡", "complexity": "medium", "estimated_impact": "信用卡逾期率降低1.5个百分点，欺诈拦截率提升至90%"},
    {"case_id": "COMP_006", "name": "关联风险智能识别", "description": "担保圈、关联企业和多头借贷的风险识别和传导分析。", "models": ["RISK_013", "RISK_014", "RISK_016"], "demand_ids": ["DEMAND_013", "DEMAND_014", "DEMAND_016"], "scenario": "信贷风控-关联风险", "complexity": "high", "estimated_impact": "担保圈风险识别率提升至85%，避免连锁违约"},
    {"case_id": "COMP_007", "name": "贷后风险监控与预警", "description": "贷款发放后的资金流向监控、风险排查和预警提醒。", "models": ["RISK_015", "RISK_017", "RISK_008"], "demand_ids": ["DEMAND_015", "DEMAND_017", "DEMAND_008"], "scenario": "信贷风控-贷后管理", "complexity": "medium", "estimated_impact": "风险预警准确率提升至88%，贷后管理效率提升60%"},
    {"case_id": "COMP_008", "name": "内部评级体系建设", "description": "PD模型、LGD模型和风险定价组合，构建内部评级体系。", "models": ["RISK_018", "RISK_019", "RISK_020", "RISK_024"], "demand_ids": ["DEMAND_018", "DEMAND_019", "DEMAND_020", "DEMAND_024"], "scenario": "信贷风控-内部评级", "complexity": "high", "estimated_impact": "内部评级体系覆盖100%，资本计量更加精准"},
    {"case_id": "COMP_009", "name": "新客获取与转化营销", "description": "从新客识别、意向判断到首贷转化的全流程精准营销。", "models": ["MKT_001", "MKT_002", "MKT_025", "MKT_005"], "demand_ids": ["DEMAND_036", "DEMAND_037", "DEMAND_060", "DEMAND_040"], "scenario": "客户营销-新客获取", "complexity": "high", "estimated_impact": "新客首贷转化率从2.3%提升至6.8%"},
    {"case_id": "COMP_010", "name": "存量客户深度经营", "description": "存量客户的交叉销售、偏好分析和价值提升综合方案。", "models": ["MKT_003", "MKT_004", "MKT_007", "MKT_019"], "demand_ids": ["DEMAND_038", "DEMAND_039", "DEMAND_042", "DEMAND_054"], "scenario": "客户营销-存量经营", "complexity": "high", "estimated_impact": "户均产品数从2.3提升至3.5，交叉销售成功率提升25%"},
    {"case_id": "COMP_011", "name": "客户流失预警与留存", "description": "客户流失预测、沉睡唤醒和产品偏好匹配的组合挽留策略。", "models": ["MKT_009", "MKT_008", "MKT_004", "MKT_018"], "demand_ids": ["DEMAND_044", "DEMAND_043", "DEMAND_039", "DEMAND_053"], "scenario": "客户营销-客户留存", "complexity": "medium", "estimated_impact": "客户流失率降低20%，沉睡客户唤醒率提升至25%"},
    {"case_id": "COMP_012", "name": "精准营销全链路", "description": "从客群筛选、响应预测到渠道触达和频次优化的精准营销。", "models": ["MKT_005", "MKT_006", "MKT_020", "MKT_021", "MKT_022"], "demand_ids": ["DEMAND_040", "DEMAND_041", "DEMAND_055", "DEMAND_056", "DEMAND_057"], "scenario": "客户营销-精准营销", "complexity": "high", "estimated_impact": "营销ROI提升3倍，触达成本降低40%"},
    {"case_id": "COMP_013", "name": "客户分层与差异化策略", "description": "客户分群、价值评估和生命周期管理，制定差异化经营策略。", "models": ["MKT_007", "MKT_010", "MKT_013", "MKT_023"], "demand_ids": ["DEMAND_042", "DEMAND_045", "DEMAND_048", "DEMAND_058"], "scenario": "客户营销-客群经营", "complexity": "medium", "estimated_impact": "客群经营精细化程度显著提升，高价值客户留存率提升15%"},
    {"case_id": "COMP_014", "name": "手机银行促活与运营", "description": "APP活跃促活、渠道偏好分析和事件营销组合。", "models": ["MKT_015", "MKT_020", "MKT_021", "MKT_035"], "demand_ids": ["DEMAND_050", "DEMAND_055", "DEMAND_056", "DEMAND_070"], "scenario": "客户营销-渠道运营", "complexity": "medium", "estimated_impact": "APP月活提升25%，营销触达效果提升40%"},
    {"case_id": "COMP_015", "name": "理财客群精准营销", "description": "理财产品偏好分析、多产品协同推荐和客户资产配置。", "models": ["MKT_017", "MKT_028", "MKT_029", "MKT_004"], "demand_ids": ["DEMAND_052", "DEMAND_066", "DEMAND_067", "DEMAND_039"], "scenario": "客户营销-理财营销", "complexity": "medium", "estimated_impact": "理财产品销售转化率提升35%，AUM增长18%"},
    {"case_id": "COMP_016", "name": "县域客群综合经营", "description": "农户理财、三农数据应用和农村电商客群的综合营销方案。", "models": ["MKT_011", "MKT_032", "MKT_033", "MKT_034"], "demand_ids": ["DEMAND_046", "DEMAND_067", "DEMAND_068", "DEMAND_069"], "scenario": "客户营销-县域客群", "complexity": "medium", "estimated_impact": "县域客群产品覆盖率提升30%，客户活跃度提升20%"},
    {"case_id": "COMP_017", "name": "网点运营效率提升", "description": "客流预测、智能排班和业务量预测，全面提升网点运营效率。", "models": ["OPS_001", "OPS_002", "OPS_003"], "demand_ids": ["DEMAND_071", "DEMAND_072", "DEMAND_073"], "scenario": "运营管理-网点效率", "complexity": "medium", "estimated_impact": "柜员效率提升25%，客户等待时间减少35%"},
    {"case_id": "COMP_018", "name": "网点规划与效能管理", "description": "网点布局评估、效能评价和动线优化，科学规划网点网络。", "models": ["OPS_004", "OPS_005", "OPS_007"], "demand_ids": ["DEMAND_074", "DEMAND_075", "DEMAND_077"], "scenario": "运营管理-网点规划", "complexity": "medium", "estimated_impact": "网点效能提升30%，撤并优化方案精准度提高至85%"},
    {"case_id": "COMP_019", "name": "反洗钱综合防控体系", "description": "可疑交易识别、客户洗钱评级和团伙挖掘的全方位反洗钱方案。", "models": ["OPS_009", "OPS_010", "OPS_011"], "demand_ids": ["DEMAND_079", "DEMAND_080", "DEMAND_081"], "scenario": "运营管理-反洗钱", "complexity": "high", "estimated_impact": "可疑交易识别率提升65%，监管检查零缺陷"},
    {"case_id": "COMP_020", "name": "合规管理自动化", "description": "合规制度匹配、监管报表生成和员工操作风险监测。", "models": ["OPS_012", "OPS_014", "OPS_013"], "demand_ids": ["DEMAND_082", "DEMAND_084", "DEMAND_083"], "scenario": "运营管理-合规管理", "complexity": "high", "estimated_impact": "合规审查效率提升3倍，报表编制时间缩短90%"},
    {"case_id": "COMP_021", "name": "交易风控与反欺诈", "description": "交易反欺诈实时拦截、收单商户风险监测和设备运维预测。", "models": ["OPS_015", "OPS_027", "OPS_008"], "demand_ids": ["DEMAND_085", "DEMAND_097", "DEMAND_078"], "scenario": "运营管理-交易风控", "complexity": "high", "estimated_impact": "年拦截欺诈交易3万+笔，故障率降低40%"},
    {"case_id": "COMP_022", "name": "业务流程优化", "description": "审批流程优化、开户简化、授权优化和流程挖掘的组合。", "models": ["OPS_016", "OPS_017", "OPS_018", "OPS_022"], "demand_ids": ["DEMAND_086", "DEMAND_087", "DEMAND_088", "DEMAND_092"], "scenario": "运营管理-流程优化", "complexity": "medium", "estimated_impact": "整体流程效率提升30%，客户体验显著改善"},
    {"case_id": "COMP_023", "name": "客户服务体验提升", "description": "投诉分析、智能客服和渠道服务质量评估的服务提升方案。", "models": ["OPS_019", "OPS_020", "OPS_028"], "demand_ids": ["DEMAND_089", "DEMAND_090", "DEMAND_098"], "scenario": "运营管理-客户服务", "complexity": "medium", "estimated_impact": "客服解决率提升至78%，客户满意度从82%提升至91%"},
    {"case_id": "COMP_024", "name": "智能运营中心", "description": "工单分配、报告自动化和数据质量监控的数字化运营。", "models": ["OPS_021", "OPS_033", "OPS_034"], "demand_ids": ["DEMAND_091", "DEMAND_103", "DEMAND_104"], "scenario": "运营管理-智能运营", "complexity": "high", "estimated_impact": "运营效率提升40%，数据质量达标率提升至98%"},
    {"case_id": "COMP_025", "name": "资产负债与流动性管理", "description": "流动性预测、资产负债配置和利率定价的财务管理组合。", "models": ["OPS_023", "OPS_025", "OPS_024"], "demand_ids": ["DEMAND_093", "DEMAND_095", "DEMAND_094"], "scenario": "运营管理-财资管理", "complexity": "high", "estimated_impact": "流动性覆盖率优化至监管要求以上，净息差提升0.15%"},
    {"case_id": "COMP_026", "name": "人力资源管理数字化", "description": "绩效预测、培训需求分析、人力规划和离职预警。", "models": ["OPS_029", "OPS_030", "OPS_031", "OPS_032"], "demand_ids": ["DEMAND_099", "DEMAND_100", "DEMAND_101", "DEMAND_102"], "scenario": "运营管理-人力资源", "complexity": "medium", "estimated_impact": "人力规划效率提升70%，核心岗位流失率降低40%"},
    {"case_id": "COMP_027", "name": "农户普惠金融综合方案", "description": "农户的贷款准入、反欺诈、额度测算和理财需求的综合金融方案。", "models": ["RISK_001", "RISK_002", "RISK_003", "MKT_011", "MKT_033"], "demand_ids": ["DEMAND_001", "DEMAND_002", "DEMAND_003", "DEMAND_046", "DEMAND_067"], "scenario": "综合-农户金融", "complexity": "high", "estimated_impact": "农户金融服务覆盖率提升40%，综合收入增长25%"},
    {"case_id": "COMP_028", "name": "小微企业全生命周期服务", "description": "从小微企业准入、经营分析、营销获客到退出的全周期服务。", "models": ["RISK_004", "RISK_005", "MKT_012", "RISK_009", "OPS_024"], "demand_ids": ["DEMAND_004", "DEMAND_005", "DEMAND_047", "DEMAND_009", "DEMAND_094"], "scenario": "综合-小微金融", "complexity": "high", "estimated_impact": "小微客户综合贡献度提升35%"},
    {"case_id": "COMP_029", "name": "信用卡生命周期经营", "description": "从信用卡营销、反欺诈、逾期预测到营销促活的完整闭环。", "models": ["MKT_016", "OPS_015", "RISK_012", "MKT_015"], "demand_ids": ["DEMAND_051", "DEMAND_085", "DEMAND_012", "DEMAND_050"], "scenario": "综合-信用卡", "complexity": "medium", "estimated_impact": "信用卡活跃率提升20%，逾期率降低1.2%"},
    {"case_id": "COMP_030", "name": "对公客户智能经营", "description": "对公客户的信用评级、价值贡献评估和交叉销售的组合经营。", "models": ["RISK_007", "MKT_013", "MKT_003", "RISK_008"], "demand_ids": ["DEMAND_007", "DEMAND_048", "DEMAND_038", "DEMAND_008"], "scenario": "综合-对公经营", "complexity": "medium", "estimated_impact": "对公客户产品渗透率提升30%，户均收入增长22%"},
    {"case_id": "COMP_031", "name": "绿色金融信贷评估", "description": "绿色企业和项目的环境风险评估、信用评级和额度测算。", "models": ["RISK_033", "RISK_007", "RISK_003"], "demand_ids": ["DEMAND_033", "DEMAND_007", "DEMAND_003"], "scenario": "综合-绿色金融", "complexity": "low", "estimated_impact": "绿色信贷审批效率提升50%"},
    {"case_id": "COMP_032", "name": "供应链金融风控与营销", "description": "供应链上下游企业的信用评估和金融产品交叉销售。", "models": ["RISK_031", "RISK_007", "MKT_028"], "demand_ids": ["DEMAND_031", "DEMAND_007", "DEMAND_066"], "scenario": "综合-供应链金融", "complexity": "medium", "estimated_impact": "供应链融资规模增长30%"},
    {"case_id": "COMP_033", "name": "不良资产处置优化", "description": "不良资产定价、催收排序和贷款催收预测的资产处置方案。", "models": ["RISK_034", "RISK_029", "RISK_035"], "demand_ids": ["DEMAND_034", "DEMAND_029", "DEMAND_035"], "scenario": "综合-不良处置", "complexity": "medium", "estimated_impact": "不良资产回收率提升20%"},
    {"case_id": "COMP_034", "name": "智能客服与投诉管理", "description": "智能FAQ匹配、投诉根因分析和工单自动分配的客服闭环。", "models": ["OPS_020", "OPS_019", "OPS_021"], "demand_ids": ["DEMAND_090", "DEMAND_089", "DEMAND_091"], "scenario": "运营管理-客服闭环", "complexity": "medium", "estimated_impact": "客服处理效率提升60%，人工成本降低30%"},
    {"case_id": "COMP_035", "name": "成本与预算智能管理", "description": "费用预算预测、运营成本分析和绩效预测的财务管理组合。", "models": ["OPS_026", "OPS_035", "OPS_029"], "demand_ids": ["DEMAND_096", "DEMAND_105", "DEMAND_099"], "scenario": "运营管理-成本管理", "complexity": "low", "estimated_impact": "预算偏差率从12%降至7%，运营成本降低12%"},
]

comp_path = os.path.join(SAMPLES_DIR, "composition_cases.jsonl")
with open(comp_path, "w", encoding="utf-8") as f:
    for c in COMPOSITION_CASES:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(f"[B-10] Created {comp_path} with {len(COMPOSITION_CASES)} composition cases")

# ============================================================
# B-10 also: composition_templates.json (5+ templates)
# ============================================================
TEMPLATES = [
    {
        "template_id": "TMPL_001",
        "name": "信贷全流程风控模板",
        "description": "覆盖贷前、贷中、贷后三个环节的标准化风控模型组合模板",
        "applicable_scenarios": ["个人贷款", "小微企业贷款", "农户贷款"],
        "stages": [
            {"stage": "pre_loan", "name": "贷前", "required_models": ["admission_scoring", "anti_fraud", "amount_calculation"], "optional_models": ["credit_rating"]},
            {"stage": "in_loan", "name": "贷中", "required_models": ["anomaly_detection"], "optional_models": ["early_warning"]},
            {"stage": "post_loan", "name": "贷后", "required_models": ["default_prediction"], "optional_models": ["early_warning", "priority_ranking"]}
        ],
        "typical_model_count": "4-6",
        "complexity": "high"
    },
    {
        "template_id": "TMPL_002",
        "name": "精准营销全链路模板",
        "description": "从客群筛选、响应预测到渠道触达的标准化营销模型组合模板",
        "applicable_scenarios": ["产品营销", "客户激活", "交叉销售"],
        "stages": [
            {"stage": "pre_marketing", "name": "营销前", "required_models": ["segmentation", "response_prediction", "conversion_prediction"], "optional_models": ["value_assessment"]},
            {"stage": "in_marketing", "name": "营销中", "required_models": ["preference_analysis"], "optional_models": ["cross_selling"]},
            {"stage": "post_marketing", "name": "营销后", "required_models": [], "optional_models": ["churn_prediction", "segmentation"]}
        ],
        "typical_model_count": "3-5",
        "complexity": "medium"
    },
    {
        "template_id": "TMPL_003",
        "name": "网点运营优化模板",
        "description": "网点客流、排班、效能和流程优化的标准化运营模型组合模板",
        "applicable_scenarios": ["网点管理", "厅堂运营", "设备管理"],
        "stages": [
            {"stage": "resource_planning", "name": "资源规划", "required_models": ["demand_forecasting", "resource_optimization"], "optional_models": []},
            {"stage": "daily_operation", "name": "日常运营", "required_models": ["priority_ranking"], "optional_models": ["anomaly_detection"]},
            {"stage": "performance_analysis", "name": "绩效分析", "required_models": ["value_assessment"], "optional_models": ["segmentation"]}
        ],
        "typical_model_count": "3-5",
        "complexity": "medium"
    },
    {
        "template_id": "TMPL_004",
        "name": "反洗钱合规管理模板",
        "description": "反洗钱可疑交易监测、客户洗钱评级和合规管理的标准化模板",
        "applicable_scenarios": ["反洗钱", "合规管理", "监管报送"],
        "stages": [
            {"stage": "risk_management", "name": "风险管理", "required_models": ["anomaly_detection", "anti_fraud"], "optional_models": ["early_warning"]},
            {"stage": "compliance", "name": "合规管理", "required_models": ["compliance_check"], "optional_models": []}
        ],
        "typical_model_count": "3-4",
        "complexity": "high"
    },
    {
        "template_id": "TMPL_005",
        "name": "客户全生命周期经营模板",
        "description": "从新客获取、交叉销售到流失预警的客户全生命周期模型组合模板",
        "applicable_scenarios": ["新客获取", "存量经营", "流失预警"],
        "stages": [
            {"stage": "acquisition", "name": "获客阶段", "required_models": ["conversion_prediction", "response_prediction"], "optional_models": ["segmentation"]},
            {"stage": "growth", "name": "成长阶段", "required_models": ["cross_selling", "preference_analysis"], "optional_models": ["value_assessment", "lifetime_value"]},
            {"stage": "retention", "name": "留存阶段", "required_models": ["churn_prediction"], "optional_models": ["segmentation", "priority_ranking"]}
        ],
        "typical_model_count": "4-6",
        "complexity": "high"
    },
    {
        "template_id": "TMPL_006",
        "name": "人力资源管理数字化模板",
        "description": "绩效预测、培训需求、人力资源规划和离职预警的人力资源管理模型组合",
        "applicable_scenarios": ["绩效管理", "人才发展", "人力规划"],
        "stages": [
            {"stage": "resource_planning", "name": "资源规划", "required_models": ["demand_forecasting"], "optional_models": ["resource_optimization"]},
            {"stage": "performance_analysis", "name": "绩效分析", "required_models": ["value_assessment"], "optional_models": []},
            {"stage": "risk_management", "name": "风险管理", "required_models": ["churn_prediction"], "optional_models": ["early_warning"]}
        ],
        "typical_model_count": "3-4",
        "complexity": "medium"
    }
]

templates_path = os.path.join(KNOWLEDGE_DIR, "composition_templates.json")
with open(templates_path, "w", encoding="utf-8") as f:
    json.dump(TEMPLATES, f, ensure_ascii=False, indent=2)
print(f"[B-10] Created {templates_path} with {len(TEMPLATES)} templates")

print("\n=== All generation complete! ===")
