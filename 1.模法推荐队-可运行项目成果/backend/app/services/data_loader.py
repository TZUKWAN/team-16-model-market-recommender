"""
data_loader.py — Data loading with fallback to built-in mock data.

Loads models, tags, data_fields, composition_templates, and eval sets.
When Agent B's data files do not exist, falls back to built-in dictionaries.
"""

from __future__ import annotations
import json
import logging
import glob
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    """Get the data directory path."""
    from app.core.config import get_settings
    return get_settings().DATA_DIR


def _load_json(path: Path, default: Any = None) -> Any:
    """Load a JSON file, returning default on error."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return default


def _load_jsonl(path: Path, default: Any = None) -> list[dict]:
    """Load a JSONL file, returning default on error."""
    if not path.exists():
        return default or []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return default or []


# ──────────────────────────────────────────────
# Built-in fallback data (minimal set for demos)
# ──────────────────────────────────────────────

_FALLBACK_MODELS: list[dict[str, Any]] = [
    {"model_id":"RISK_001","model_name":"农户小额贷款准入评分模型","domain":"credit_risk","business_scenario":["农户小额贷款贷前准入"],"business_stage":["pre_loan"],"customer_segment":["farmer"],"model_capability":["admission_scoring"],"input_fields_required":["customer_profile","loan_application"],"input_fields_optional":["credit_report","asset_liability"],"output_fields":["risk_score","risk_level","admission_decision"],"performance_metrics":{"auc":0.82,"ks":0.45},"applicable_conditions":"适用于农户小额信用贷款的准入评估","unsuitable_conditions":"不适用于有抵押贷款，不适用于企业贷款","compliance_boundary":"需符合涉农贷款监管要求","deployment_status":"mock_available","api_available":True,"historical_cases":["某农信社农户贷款准入项目，上线后不良率下降15%"],"tags":["农户","小额贷款","准入评分","涉农贷款"],"description":"基于农户基本信息、经营数据和征信报告的准入评分模型"},
    {"model_id":"RISK_002","model_name":"农户小额贷款反欺诈模型","domain":"credit_risk","business_scenario":["农户小额贷款贷前准入"],"business_stage":["pre_loan"],"customer_segment":["farmer"],"model_capability":["anti_fraud"],"input_fields_required":["customer_profile","anti_fraud_data","loan_application"],"input_fields_optional":["call_records","social_network"],"output_fields":["fraud_score","fraud_label","fraud_reason_code"],"performance_metrics":{"auc":0.91,"recall":0.88},"applicable_conditions":"适用于识别农户贷款中的欺诈申请","unsuitable_conditions":"不适用于无足够历史数据的新客群","compliance_boundary":"需遵守个人信息保护法","deployment_status":"mock_available","api_available":True,"historical_cases":["某省农信社反欺诈项目，年拦截欺诈申请1200+笔"],"tags":["农户","反欺诈","骗贷识别","涉农贷款"],"description":"基于多维数据识别农户贷款欺诈申请的反欺诈模型"},
    {"model_id":"RISK_003","model_name":"农户小额贷款额度测算模型","domain":"credit_risk","business_scenario":["农户小额贷款贷前准入"],"business_stage":["pre_loan"],"customer_segment":["farmer"],"model_capability":["amount_estimation"],"input_fields_required":["asset_liability","business_operation","loan_application"],"input_fields_optional":["credit_report","collateral_info"],"output_fields":["suggested_amount","amount_range","amount_basis"],"performance_metrics":{"mae":2.5,"mape":0.18},"applicable_conditions":"适用于农户生产经营性贷款额度测算","unsuitable_conditions":"不适用于纯消费性贷款","compliance_boundary":"额度不超过监管规定的农户小额贷款上限","deployment_status":"mock_available","api_available":True,"historical_cases":["某农信社额度测算项目，测算准确率82%"],"tags":["农户","额度测算","小额贷款","涉农贷款"],"description":"结合农户资产负债和经营状况测算合理贷款额度的模型"},
    {"model_id":"RISK_004","model_name":"小微企业贷前准入模型","domain":"credit_risk","business_scenario":["小微企业贷前准入","小微企业贷款"],"business_stage":["pre_loan"],"customer_segment":["small_micro_enterprise"],"model_capability":["admission_scoring"],"input_fields_required":["customer_profile","business_operation","loan_application"],"input_fields_optional":["credit_report","asset_liability","guarantee_info"],"output_fields":["risk_score","risk_level","admission_decision"],"performance_metrics":{"auc":0.85,"ks":0.48},"applicable_conditions":"适用于小微企业信用贷款准入评估","unsuitable_conditions":"不适用于初创期无经营历史的企业","compliance_boundary":"需符合普惠金融监管要求","deployment_status":"mock_available","api_available":True,"historical_cases":["某城商行小微准入项目，审批效率提升40%"],"tags":["小微企业","准入评分","普惠金融","信用贷款"],"description":"面向小微企业的贷前准入评分模型"},
    {"model_id":"RISK_006","model_name":"小微企业反欺诈模型","domain":"credit_risk","business_scenario":["小微企业贷前准入","小微企业贷款"],"business_stage":["pre_loan"],"customer_segment":["small_micro_enterprise"],"model_capability":["anti_fraud"],"input_fields_required":["customer_profile","anti_fraud_data","business_operation"],"input_fields_optional":["social_network","guarantee_info"],"output_fields":["fraud_score","fraud_label","risk_indicators"],"performance_metrics":{"auc":0.88,"recall":0.85},"applicable_conditions":"适用于识别小微企业贷款中的欺诈行为","unsuitable_conditions":"不适用于无经营数据的空壳公司识别","compliance_boundary":"需遵守个人信息保护法","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行小微反欺诈项目，欺诈识别准确率85%"],"tags":["小微企业","反欺诈","普惠金融"],"description":"识别小微企业贷款欺诈申请的反欺诈模型"},
    {"model_id":"RISK_008","model_name":"对公贷款逾期风险预测模型","domain":"credit_risk","business_scenario":["对公贷款贷后预警","对公贷款"],"business_stage":["post_loan"],"customer_segment":["corporate"],"model_capability":["default_prediction"],"input_fields_required":["repayment_record","transaction_history","business_operation"],"input_fields_optional":["industry_data","asset_liability"],"output_fields":["default_probability","risk_score","risk_trend"],"performance_metrics":{"auc":0.84,"precision":0.76},"applicable_conditions":"适用于对公贷款的逾期风险预测","unsuitable_conditions":"不适用于政策性贷款","compliance_boundary":"需符合贷后管理监管指引","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行对公预警项目，提前30天预警准确率76%"],"tags":["对公客户","逾期预测","贷后预警","企业贷款"],"description":"对对公客户进行逾期风险预测的模型"},
    {"model_id":"RISK_009","model_name":"对公贷款贷后预警模型","domain":"credit_risk","business_scenario":["对公贷款贷后预警","对公贷款"],"business_stage":["post_loan"],"customer_segment":["corporate"],"model_capability":["early_warning"],"input_fields_required":["transaction_history","repayment_record","business_operation"],"input_fields_optional":["industry_data","asset_liability","social_network"],"output_fields":["warning_level","warning_score","warning_reason","suggested_action"],"performance_metrics":{"auc":0.86,"recall":0.82},"applicable_conditions":"适用于对公贷款的贷后风险预警","unsuitable_conditions":"不适用于已进入不良的贷款","compliance_boundary":"预警信息仅限内部风控使用","deployment_status":"mock_available","api_available":True,"historical_cases":["某大型银行贷后预警项目，预警召回率82%"],"tags":["对公客户","贷后预警","预警监测","企业贷款"],"description":"对对公贷款进行多维度风险预警的综合模型"},
    {"model_id":"RISK_026","model_name":"客户风险分层模型","domain":"credit_risk","business_scenario":["客户风险管理"],"business_stage":["pre_loan","in_loan","post_loan"],"customer_segment":["individual","small_micro_enterprise","corporate"],"model_capability":["credit_rating"],"input_fields_required":["customer_profile","credit_report","transaction_history"],"input_fields_optional":["business_operation","industry_data"],"output_fields":["risk_tier","risk_score","tier_characteristics"],"performance_metrics":{"entropy":0.72,"silhouette":0.35},"applicable_conditions":"适用于全行客户风险分层管理","unsuitable_conditions":"不适用于新开户无交易记录的客户","compliance_boundary":"风险分层结果供内部使用","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行客户分层项目，实现客户全生命周期风险视图"],"tags":["风险分层","客户评级","全生命周期"],"description":"基于客户多维数据进行风险分层和画像的模型"},
    {"model_id":"MKT_001","model_name":"县域新客首贷转化预测模型","domain":"customer_marketing","business_scenario":["县域新客营销","首贷营销"],"business_stage":["marketing","pre_loan"],"customer_segment":["county_new_customer"],"model_capability":["conversion_prediction"],"input_fields_required":["customer_profile","transaction_history"],"input_fields_optional":["channel_behavior","marketing_history","credit_report"],"output_fields":["conversion_probability","interest_score","next_best_action"],"performance_metrics":{"auc":0.85,"lift_top10pct":3.2},"applicable_conditions":"适用于县域新客的首贷转化预测","unsuitable_conditions":"不适用于已有贷款的存量客户","compliance_boundary":"营销需符合个人信息保护法","deployment_status":"mock_available","api_available":True,"historical_cases":["某县域银行首贷转化项目，转化率提升2.8倍"],"tags":["新客","首贷","营销转化","响应预测","县域新客"],"description":"预测县域新客户转化为首贷客户概率的模型"},
    {"model_id":"MKT_005","model_name":"客户响应率预测模型","domain":"customer_marketing","business_scenario":["营销活动优化","客户经营"],"business_stage":["marketing"],"customer_segment":["individual","existing_customer"],"model_capability":["response_prediction"],"input_fields_required":["customer_profile","marketing_history","channel_behavior"],"input_fields_optional":["transaction_history","app_usage"],"output_fields":["response_probability","preferred_channel","best_time"],"performance_metrics":{"auc":0.81,"lift_top20pct":2.6},"applicable_conditions":"适用于预测客户对营销活动的响应概率","unsuitable_conditions":"不适用于无历史营销活动数据的新客群","compliance_boundary":"营销频次需符合监管要求","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行营销响应项目，响应率提升2.2倍"],"tags":["响应率","营销","客户经营","预测"],"description":"预测客户对营销活动响应概率的模型"},
    {"model_id":"MKT_006","model_name":"营销名单排序模型","domain":"customer_marketing","business_scenario":["营销活动优化","客户经营"],"business_stage":["marketing"],"customer_segment":["individual","existing_customer","county_new_customer"],"model_capability":["ranking"],"input_fields_required":["conversion_probability","customer_profile","transaction_history"],"input_fields_optional":["channel_behavior","marketing_history"],"output_fields":["ranked_list","priority_score","segment_label"],"performance_metrics":{"precision@top10pct":0.78},"applicable_conditions":"适用于生成排序后的营销跟进名单","unsuitable_conditions":"不适用于不分优先级的全面营销","compliance_boundary":"名单排序仅供营销参考","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行名单排序项目，营销ROI提升3倍"],"tags":["名单排序","营销","优先级","客户排序"],"description":"对营销目标客户进行优先级排序的模型"},
    {"model_id":"MKT_007","model_name":"高价值客户识别模型","domain":"customer_marketing","business_scenario":["客户价值管理","客户经营"],"business_stage":["marketing"],"customer_segment":["individual","existing_customer"],"model_capability":["customer_value"],"input_fields_required":["customer_profile","transaction_history","asset_liability"],"input_fields_optional":["channel_behavior","marketing_history"],"output_fields":["customer_value_score","value_tier","value_drivers"],"performance_metrics":{"lift_top20pct":3.5,"precision":0.82},"applicable_conditions":"适用于识别和细分高价值客户","unsuitable_conditions":"不适用于新开户客户","compliance_boundary":"价值评估仅供内部经营参考","deployment_status":"mock_available","api_available":True,"historical_cases":["某银行高价值客户项目，VIP客户留存率提升25%"],"tags":["高价值","客户识别","价值管理","客户经营"],"description":"基于客户贡献度识别高价值客户的模型"},
    {"model_id":"MKT_025","model_name":"首贷户白名单推荐模型","domain":"customer_marketing","business_scenario":["首贷营销","普惠营销"],"business_stage":["marketing","pre_loan"],"customer_segment":["county_new_customer","small_micro_enterprise","farmer"],"model_capability":["conversion_prediction"],"input_fields_required":["customer_profile","transaction_history","credit_report"],"input_fields_optional":["business_operation","channel_behavior"],"output_fields":["whitelist_score","recommended_limit","priority_level"],"performance_metrics":{"auc":0.83,"precision@top20pct":0.76},"applicable_conditions":"适用于首贷户白名单筛选和推荐","unsuitable_conditions":"不适用于已有贷款记录的客户","compliance_boundary":"首贷户认定需符合普惠金融口径","deployment_status":"mock_available","api_available":False,"historical_cases":["某银行首贷户白名单项目，白名单转化率32%"],"tags":["首贷","白名单","推荐","普惠金融","新客"],"description":"识别和推荐可发展为首贷户的优质客户模型"},
    {"model_id":"OPS_001","model_name":"网点客流预测模型","domain":"operation_management","business_scenario":["网点运营"],"business_stage":["运营"],"customer_segment":["individual"],"model_capability":["traffic_prediction"],"input_fields_required":["branch_operations","historical_traffic"],"input_fields_optional":["weather_data","holiday_data","events_data"],"output_fields":["predicted_traffic","peak_hours","resource_needs"],"performance_metrics":{"mape":0.14},"applicable_conditions":"适用于网点日常客流量预测","unsuitable_conditions":"不适用于突发性公共卫生事件场景","compliance_boundary":"预测数据仅用于内部运营管理","deployment_status":"mock_available","api_available":False,"historical_cases":["某银行网点客流预测项目，排队时间降低25%"],"tags":["网点","客流","预测","运营管理"],"description":"网点日常客流量预测模型"},
    {"model_id":"OPS_007","model_name":"投诉风险预警模型","domain":"operation_management","business_scenario":["客户体验","风险防控"],"business_stage":["运营"],"customer_segment":["individual","existing_customer","corporate"],"model_capability":["early_warning"],"input_fields_required":["customer_complaint","service_records","customer_profile"],"input_fields_optional":["channel_behavior","social_media_data"],"output_fields":["complaint_risk_score","risk_category","suggested_action"],"performance_metrics":{"auc":0.81,"recall":0.76},"applicable_conditions":"适用于提前预警可能的客户投诉事件","unsuitable_conditions":"不适用于无历史服务记录的客户","compliance_boundary":"投诉预警需符合消费者权益保护要求","deployment_status":"mock_available","api_available":False,"historical_cases":["某银行投诉预警项目，投诉率降低20%"],"tags":["投诉","预警","客户体验","风险防控"],"description":"提前预警可能的客户投诉事件"},
]

_FALLBACK_TAGS: dict[str, Any] = {
    "meta": {"version": "1.0", "description": "Minimal built-in fallback tag taxonomy"},
    "tags": [
        # Domain
        {"key": "credit_risk", "name": "信贷风控", "category": "domain",
         "synonyms": ["风控", "信用风险", "信贷风险", "贷款风险", "风险控制"],
         "description": "信贷业务相关的风险控制"},
        {"key": "customer_marketing", "name": "客户营销", "category": "domain",
         "synonyms": ["营销", "客户营销", "市场", "获客", "转化", "交叉销售"],
         "description": "客户获取、转化和经营"},
        {"key": "operation_management", "name": "运营管理", "category": "domain",
         "synonyms": ["运营", "管理", "运营管理", "网点", "效率"],
         "description": "银行日常运营和管理"},
        # Business stage
        {"key": "pre_loan", "name": "贷前", "category": "business_stage",
         "synonyms": ["贷前", "准入", "申请", "审批", "贷前营销"],
         "description": "贷款发放前的阶段"},
        {"key": "in_loan", "name": "贷中", "category": "business_stage",
         "synonyms": ["贷中", "放款", "交易监测"],
         "description": "贷款存续期间"},
        {"key": "post_loan", "name": "贷后", "category": "business_stage",
         "synonyms": ["贷后", "贷后管理", "预警", "催收", "逾期"],
         "description": "贷款发放后的管理阶段"},
        {"key": "marketing", "name": "营销", "category": "business_stage",
         "synonyms": ["营销", "推广", "触达", "获客", "拉新"],
         "description": "营销推广阶段"},
        # Customer segment
        {"key": "farmer", "name": "农户", "category": "customer_segment",
         "synonyms": ["农户", "农民", "农村", "农业", "种植户"],
         "description": "农户客群"},
        {"key": "small_micro_enterprise", "name": "小微企业", "category": "customer_segment",
         "synonyms": ["小微企业", "小微", "中小企业", "个体工商户"],
         "description": "小微企业客群"},
        {"key": "corporate", "name": "对公客户", "category": "customer_segment",
         "synonyms": ["对公", "企业", "公司", "机构客户"],
         "description": "对公企业客群"},
        {"key": "individual", "name": "个人客户", "category": "customer_segment",
         "synonyms": ["个人", "零售", "消费者"],
         "description": "个人零售客群"},
        {"key": "county_new_customer", "name": "县域新客", "category": "customer_segment",
         "synonyms": ["县域新客", "新客", "县域客户", "县域首贷"],
         "description": "县域新拓展客户"},
        {"key": "existing_customer", "name": "存量客户", "category": "customer_segment",
         "synonyms": ["存量", "老客", "存量客户", "已有客户"],
         "description": "已在银行有业务的客户"},
        # Model capability
        {"key": "admission_scoring", "name": "准入评分", "category": "model_capability",
         "synonyms": ["准入评分", "能不能贷", "评分", "准入", "评分卡"],
         "description": "贷款准入评分能力"},
        {"key": "anti_fraud", "name": "反欺诈", "category": "model_capability",
         "synonyms": ["反欺诈", "欺诈识别", "欺诈检测", "骗贷识别"],
         "description": "欺诈风险识别能力"},
        {"key": "default_prediction", "name": "违约预测", "category": "model_capability",
         "synonyms": ["违约预测", "逾期预测", "违约概率", "PD模型"],
         "description": "违约/逾期概率预测"},
        {"key": "early_warning", "name": "预警监测", "category": "model_capability",
         "synonyms": ["预警", "监测", "风险预警", "提前发现", "预警名单"],
         "description": "风险预警和监测能力"},
        {"key": "amount_estimation", "name": "额度测算", "category": "model_capability",
         "synonyms": ["额度", "额度测算", "授信", "贷款额度"],
         "description": "贷款额度测算能力"},
        {"key": "conversion_prediction", "name": "转化预测", "category": "model_capability",
         "synonyms": ["转化预测", "转化", "容易转化", "响应预测", "转化概率"],
         "description": "客户转化概率预测"},
        {"key": "response_prediction", "name": "响应率预测", "category": "model_capability",
         "synonyms": ["响应率", "响应", "响应预测", "营销响应"],
         "description": "营销活动响应预测"},
        {"key": "ranking", "name": "名单排序", "category": "model_capability",
         "synonyms": ["排序", "名单排序", "优先级", "客户排序"],
         "description": "客户名单排序能力"},
        {"key": "customer_value", "name": "客户价值识别", "category": "model_capability",
         "synonyms": ["价值识别", "客户价值", "高价值", "贡献度"],
         "description": "客户价值识别能力"},
        {"key": "credit_rating", "name": "信用评级", "category": "model_capability",
         "synonyms": ["信用评级", "评级", "信用评分"],
         "description": "客户信用评级能力"},
    ]
}

_FALLBACK_DATA_FIELDS: list[dict[str, Any]] = [
    {"field_key": "customer_profile", "name": "客户画像", "category": "customer_info",
     "sensitivity": "high", "description": "客户基本信息、年龄、性别、职业等"},
    {"field_key": "credit_report", "name": "征信报告", "category": "credit_info",
     "sensitivity": "high", "description": "央行征信报告数据"},
    {"field_key": "transaction_history", "name": "交易流水", "category": "transaction",
     "sensitivity": "high", "description": "账户交易流水记录"},
    {"field_key": "repayment_record", "name": "还款记录", "category": "transaction",
     "sensitivity": "high", "description": "历史还款情况记录"},
    {"field_key": "loan_application", "name": "贷款申请信息", "category": "loan_info",
     "sensitivity": "high", "description": "贷款申请表信息"},
    {"field_key": "business_operation", "name": "经营信息", "category": "business_info",
     "sensitivity": "high", "description": "企业经营数据"},
    {"field_key": "asset_liability", "name": "资产负债信息", "category": "financial",
     "sensitivity": "high", "description": "资产负债状况"},
    {"field_key": "marketing_history", "name": "营销触达记录", "category": "marketing",
     "sensitivity": "medium", "description": "历史营销触达和响应记录"},
    {"field_key": "channel_behavior", "name": "渠道行为", "category": "behavior",
     "sensitivity": "medium", "description": "线上线下渠道行为数据"},
    {"field_key": "branch_operations", "name": "网点运营数据", "category": "operations",
     "sensitivity": "low", "description": "网点运营统计数据"},
    {"field_key": "anti_fraud_data", "name": "反欺诈数据", "category": "risk_info",
     "sensitivity": "high", "description": "欺诈识别相关数据"},
    {"field_key": "collateral_info", "name": "抵质押物信息", "category": "collateral",
     "sensitivity": "high", "description": "抵质押物评估和管理数据"},
]

_FALLBACK_COMPOSITION_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "COMP_PRE_LOAN",
        "name": "贷前风控组合",
        "scenario": "贷前风控",
        "applicable_scenarios": ["农户小额贷款贷前准入", "小微企业贷前准入", "贷前风控", "准入风控"],
        "domains": ["credit_risk"],
        "business_stages": ["pre_loan"],
        "description": "贷款发放前的准入风控流程",
        "stages": [
            {
                "name": "反欺诈检查",
                "required_models": ["anti_fraud"],
                "input_requirements": ["customer_profile", "anti_fraud_data"],
                "output_requirements": ["fraud_score", "fraud_label"],
            },
            {
                "name": "准入评分",
                "required_models": ["admission_scoring"],
                "input_requirements": ["customer_profile", "credit_report"],
                "output_requirements": ["risk_score", "risk_level"],
            },
            {
                "name": "额度测算",
                "required_models": ["amount_estimation"],
                "input_requirements": ["asset_liability", "business_operation"],
                "output_requirements": ["suggested_amount", "amount_range"],
            },
        ],
        "explanations": {
            "business": "本组合覆盖贷前准入全流程：先做反欺诈检查排除骗贷风险，再做准入评分评估客户信用，最后测算合理贷款额度。",
            "technical": "三阶段流水线架构：反欺诈模型(规则+XGBoost) → 准入评分模型(逻辑回归评分卡) → 额度测算模型(决策树+业务规则)。",
            "management": "建议优先部署反欺诈模型降低欺诈损失，再部署准入评分标准化审批流程，额度测算模型可后续迭代。"
        }
    },
    {
        "template_id": "COMP_POST_LOAN",
        "name": "贷后预警组合",
        "scenario": "贷后预警",
        "applicable_scenarios": ["对公贷款贷后预警", "贷款逾期预警", "贷后风控"],
        "domains": ["credit_risk"],
        "business_stages": ["post_loan"],
        "description": "贷款发放后的风险预警管理流程",
        "stages": [
            {
                "name": "逾期风险预测",
                "required_models": ["default_prediction"],
                "input_requirements": ["repayment_record", "transaction_history"],
                "output_requirements": ["default_probability", "risk_score"],
            },
            {
                "name": "客户价值分层",
                "required_models": ["customer_value"],
                "input_requirements": ["customer_profile", "transaction_history"],
                "output_requirements": ["customer_value_score", "customer_tier"],
            },
            {
                "name": "预警名单排序",
                "required_models": ["ranking"],
                "input_requirements": ["default_probability", "customer_value_score"],
                "output_requirements": ["warning_list", "priority_order"],
            },
        ],
        "explanations": {
            "business": "先预测每位客户的逾期概率，再结合客户价值进行分层，最后输出风险预警名单供客户经理跟进。",
            "technical": "三阶段分析：逾期预测(XGBoost) → 价值分层(RFM+KMeans) → 综合排序(加权评分表)。",
            "management": "建议按风险等级配置差异化贷后管理策略，高风低值客户优先催收。"
        }
    },
    {
        "template_id": "COMP_MARKETING",
        "name": "营销转化组合",
        "scenario": "客户营销",
        "applicable_scenarios": ["县域新客首贷营销", "客户营销转化", "首贷营销"],
        "domains": ["customer_marketing"],
        "business_stages": ["marketing", "pre_loan"],
        "description": "客户营销转化全流程",
        "stages": [
            {
                "name": "转化预测",
                "required_models": ["conversion_prediction"],
                "input_requirements": ["customer_profile", "transaction_history", "marketing_history"],
                "output_requirements": ["conversion_probability", "interest_score"],
            },
            {
                "name": "营销名单排序",
                "required_models": ["ranking"],
                "input_requirements": ["conversion_probability", "customer_profile"],
                "output_requirements": ["ranked_list", "priority_score"],
            },
        ],
        "explanations": {
            "business": "先预测每位客户的转化可能性，再按优先级排序生成营销名单，提升营销效率和ROI。",
            "technical": "两阶段营销引擎：转化预测(GBDT+LR) → 名单排序(多目标优化评分)。",
            "management": "建议A/B测试验证模型效果，初期覆盖20%客群，效果达标后全量推广。"
        }
    },
]

# ─── PUBLIC API ────────────────────────────────


def _has_any(text: str, keywords: list[str]) -> bool:
    """Return whether any keyword appears in text."""
    return any(kw in text for kw in keywords)


def _append_unique(items: list[str], value: str) -> None:
    """Append value once while preserving order."""
    if value and value not in items:
        items.append(value)


def _infer_official_tags(text: str, domain: str) -> list[str]:
    """Infer internal tag keys from official model name/description text."""
    tags: list[str] = []

    _append_unique(tags, domain)

    rules = [
        ("pre_loan", ["贷前", "准入", "申请评分", "审批", "A卡"]),
        ("in_loan", ["贷中", "存续", "用款", "B卡", "行为评分"]),
        ("post_loan", ["贷后", "催收", "逾期", "违约", "不良", "流失预警"]),
        ("pre_marketing", ["营销", "获客", "拓客", "潜客", "促活", "推荐"]),
        ("in_marketing", ["营销", "触达", "转化", "促活"]),
        ("daily_operation", ["网点", "柜面", "排队", "客流", "运营"]),
        ("risk_management", ["风险", "风控", "预警", "反欺诈", "反诈", "反洗钱"]),
        ("compliance", ["合规", "监管", "可疑交易", "反洗钱"]),
        ("farmer", ["农户", "涉农", "三农", "农村"]),
        ("rural_area", ["县域", "乡镇", "农村"]),
        ("small_micro_enterprise", ["小微", "个体工商", "商户", "经营贷款"]),
        ("corporate", ["对公", "企业", "公司", "法人", "经营"]),
        ("individual", ["个人", "对私", "零售", "自然人"]),
        ("high_net_worth", ["高端", "高净值", "财富", "AUM", "aum", "贵宾"]),
        ("new_customer", ["新客", "潜客", "新增", "拓客"]),
        ("existing_customer", ["存量", "老客户", "维稳", "留存"]),
        ("dormant_customer", ["沉睡", "睡眠", "促活"]),
        ("churned_customer", ["流失", "挽留", "维稳"]),
        ("small_loan", ["小额", "垒小户", "阳光E贷"]),
        ("agricultural_loan", ["农贷", "涉农", "农户"]),
        ("first_loan", ["首贷", "首次贷款"]),
        ("consumer_loan", ["消费贷", "消费贷款", "个人消费贷", "未用信", "用信"]),
        ("credit_card", ["信用卡", "贷记卡", "分期"]),
        ("corporate_loan", ["对公贷款", "经营贷款", "企业贷款"]),
        ("financial_product", ["理财", "财富", "产品推荐", "中间业务"]),
        ("deposit", ["存款", "增存", "AUM", "aum", "余额", "代发"]),
        ("mobile_banking", ["手机银行", "E路有我", "移动银行"]),
        ("admission_scoring", ["准入", "评分卡", "申请评分", "贷前准入", "A卡"]),
        ("anti_fraud", ["欺诈", "反欺诈", "反诈", "涉诈", "骗贷"]),
        ("credit_rating", ["评级", "信用评分", "评分模型"]),
        ("amount_calculation", ["额度", "授信", "固定额度", "调额"]),
        ("default_prediction", ["逾期", "违约", "坏账", "不良", "PD", "B卡", "行为评分"]),
        ("early_warning", ["预警", "提前预测", "风险监控"]),
        ("conversion_prediction", ["转化", "办理", "购买", "获客", "拓客", "促活", "用信率", "新增借据"]),
        ("response_prediction", ["响应", "营销响应"]),
        ("churn_prediction", ["流失", "挽留", "维稳", "留存"]),
        ("value_assessment", ["价值", "高价值", "贡献度", "AUM", "aum"]),
        ("segmentation", ["分层", "客群", "分类", "画像"]),
        ("demand_forecasting", ["需求", "偏好", "预测"]),
        ("anomaly_detection", ["异常", "可疑", "涉诈"]),
        ("risk_pricing", ["利率", "定价"]),
        ("priority_ranking", ["名单", "排序", "优先级", "白名单"]),
        ("compliance_check", ["合规", "监管", "反洗钱", "可疑交易"]),
        ("cross_selling", ["交叉营销", "产品推荐", "中间业务", "联动", "新增借据"]),
        ("lifetime_value", ["生命周期", "长期价值", "价值"]),
        ("preference_analysis", ["偏好", "推荐", "匹配"]),
        ("anti_money_laundering", ["反洗钱", "AML", "可疑交易"]),
        ("risk_score", ["风险评分", "评分"]),
        ("probability", ["概率", "可能性", "预测"]),
        ("ranked_list", ["名单", "排序", "清单"]),
        ("alert_signal", ["预警", "信号"]),
        ("customer_profile", ["客户", "用户", "画像"]),
        ("credit_report", ["征信"]),
        ("transaction_data", ["交易", "流水", "AUM", "aum", "余额", "用款", "代发"]),
        ("repayment_history", ["还款", "逾期", "违约"]),
        ("loan_application", ["贷款", "申请", "贷前", "准入"]),
        ("business_data", ["经营", "商户", "企业", "小微"]),
        ("asset_liability", ["资产", "负债", "AUM", "aum", "余额"]),
        ("marketing_history", ["营销", "触达", "促活", "转化"]),
        ("channel_behavior", ["手机银行", "渠道", "线上", "ETC", "E路有我", "贷记卡"]),
    ]
    for tag, keywords in rules:
        if _has_any(text, keywords):
            _append_unique(tags, tag)

    return tags


def _infer_official_fields(tags: list[str], text: str) -> tuple[list[str], list[str]]:
    """Infer input and output fields for sparse official catalog records."""
    inputs: list[str] = ["customer_profile"]
    outputs: list[str] = []

    if _has_any(text, ["交易", "流水", "AUM", "aum", "余额", "用款", "活期"]):
        _append_unique(inputs, "transaction_history")
    if _has_any(text, ["征信", "信用报告"]):
        _append_unique(inputs, "credit_report")
    if _has_any(text, ["贷款", "申请", "贷前", "准入", "授信"]):
        _append_unique(inputs, "loan_application")
    if _has_any(text, ["经营", "企业", "小微", "商户", "收单"]):
        _append_unique(inputs, "business_operation")
    if _has_any(text, ["营销", "触达", "促活", "转化", "推荐"]):
        _append_unique(inputs, "marketing_history")
    if _has_any(text, ["手机银行", "ETC", "E路有我", "渠道"]):
        _append_unique(inputs, "channel_behavior")
    if _has_any(text, ["还款", "逾期", "违约"]):
        _append_unique(inputs, "repayment_record")

    output_rules = [
        ("risk_score", ["risk_score", "admission_scoring", "credit_rating", "default_prediction"]),
        ("risk_level", ["risk_level", "early_warning", "default_prediction"]),
        ("admission_decision", ["admission_scoring"]),
        ("fraud_score", ["anti_fraud", "anomaly_detection"]),
        ("conversion_probability", ["conversion_prediction", "response_prediction"]),
        ("churn_probability", ["churn_prediction"]),
        ("customer_value_score", ["value_assessment", "lifetime_value"]),
        ("recommended_amount", ["amount_calculation"]),
        ("ranked_list", ["priority_ranking", "ranked_list"]),
        ("alert_signal", ["early_warning", "alert_signal", "compliance_check"]),
        ("recommendation_result", ["preference_analysis", "cross_selling", "financial_product"]),
    ]
    tag_set = set(tags)
    for output, required_tags in output_rules:
        if tag_set & set(required_tags):
            _append_unique(outputs, output)

    if not outputs:
        _append_unique(outputs, "score")
        _append_unique(outputs, "probability")

    return inputs, outputs


def _adapt_official_model(record: dict[str, Any]) -> dict[str, Any]:
    """Convert official catalog rows to the internal model schema."""
    name = record.get("canonical_name", "") or record.get("model_name", "")
    description = record.get("description", "")
    domain = record.get("domain", "")
    text = f"{name}\n{description}"
    tags = _infer_official_tags(text, domain)
    inputs, outputs = _infer_official_fields(tags, text)

    capabilities = [
        t for t in tags
        if t in {
            "admission_scoring", "anti_fraud", "credit_rating", "amount_calculation",
            "default_prediction", "early_warning", "conversion_prediction",
            "response_prediction", "churn_prediction", "value_assessment",
            "segmentation", "demand_forecasting", "anomaly_detection",
            "risk_pricing", "priority_ranking", "resource_optimization",
            "compliance_check", "cross_selling", "lifetime_value",
            "preference_analysis", "anti_money_laundering",
        }
    ]

    def list_from_record(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        text_value = str(value).strip()
        return [text_value] if text_value else []

    enriched_customer_segment = list_from_record(record.get("customer_segment"))
    inferred_customer_segment = [
        t for t in tags
        if t in {
            "farmer", "rural_area", "small_micro_enterprise", "corporate",
            "individual", "high_net_worth", "new_customer", "existing_customer",
            "dormant_customer", "churned_customer", "young_customer",
        }
    ]
    performance_metrics = record.get("performance_metrics") if isinstance(record.get("performance_metrics"), dict) else {}
    historical_cases = list_from_record(record.get("historical_cases"))
    return {
        "model_id": record.get("model_id", ""),
        "model_name": name,
        "canonical_name": name,
        "aliases": record.get("aliases", []),
        "domain": domain,
        "business_scenario": [name],
        "business_stage": [t for t in tags if t in {"pre_loan", "in_loan", "post_loan", "pre_marketing", "in_marketing", "post_marketing", "daily_operation", "risk_management", "compliance"}],
        "customer_segment": enriched_customer_segment or inferred_customer_segment,
        "model_capability": capabilities or [domain],
        "input_fields_required": inputs,
        "input_fields_optional": [],
        "output_fields": outputs,
        "performance_metrics": performance_metrics,
        "applicable_conditions": description,
        "unsuitable_conditions": "以官方模型目录描述的目标用户和业务边界为准。",
        "compliance_boundary": "官方模型市场目录模型，需按行内数据安全、个人信息保护和模型管理要求使用。",
        "deployment_status": "official_catalog",
        "api_available": False,
        "historical_cases": historical_cases,
        "tags": tags,
        "description": description,
        "source": "official",
        "catalog_version": str(record.get("catalog_version") or "official-v1"),
        "search_text": text,
        "total_questions": record.get("total_questions", 0),
    }


def load_models() -> list[dict[str, Any]]:
    """Load demo models and official catalog models into the internal schema."""
    data_dir = _get_data_dir()
    knowledge_dir = data_dir / "knowledge"
    models = []
    for prefix in ("RISK", "MKT", "OPS"):
        for fp in sorted(knowledge_dir.glob(f"{prefix}_*.json")):
            m = _load_json(fp)
            if m and isinstance(m, dict):
                m["source"] = "demo"
                m["catalog_version"] = "demo-v1"
                models.append(m)

    official_models = [
        _adapt_official_model(record)
        for record in load_official_models()
        if record.get("model_id")
    ]

    if official_models:
        existing_ids = {m.get("model_id") for m in models}
        models.extend(m for m in official_models if m.get("model_id") not in existing_ids)

    if models:
        logger.info(f"Loaded {len(models)} models from individual JSON files")
        return models
    logger.info(f"Using built-in fallback models ({len(_FALLBACK_MODELS)} models)")
    return [dict(m, source="demo", catalog_version="demo-v1") for m in _FALLBACK_MODELS]


def load_tags() -> dict[str, Any]:
    """Load tag taxonomy from data/knowledge/tags.json or fallback."""
    data_dir = _get_data_dir()
    tags_file = data_dir / "knowledge" / "tags.json"
    tags = _load_json(tags_file)
    if tags and isinstance(tags, dict) and any(k.endswith('_tags') for k in tags):
        all_tags = []
        for cat_key, cat_tags in tags.items():
            if cat_key.endswith('_tags') and isinstance(cat_tags, list):
                category = cat_key.replace('_tags', '')
                for t in cat_tags:
                    t = dict(t)
                    t['category'] = category
                    all_tags.append(t)
        logger.info(f"Loaded {len(all_tags)} tags from {tags_file}")
        return {"tags": all_tags}
    if tags and isinstance(tags, dict) and "tags" in tags:
        logger.info(f"Loaded tags from {tags_file}")
        return tags
    logger.info("Using built-in fallback tags")
    return _FALLBACK_TAGS


def load_data_fields() -> list[dict[str, Any]]:
    """Load data field dictionary from data/knowledge/data_fields.json or fallback."""
    data_dir = _get_data_dir()
    fields_file = data_dir / "knowledge" / "data_fields.json"
    data = _load_json(fields_file)
    if data and isinstance(data, dict) and "fields" in data:
        fields = data["fields"]
        if isinstance(fields, list):
            logger.info(f"Loaded {len(fields)} data fields from {fields_file}")
            return fields
    if data and isinstance(data, list):
        logger.info(f"Loaded {len(data)} data fields from {fields_file}")
        return data
    logger.info("Using built-in fallback data fields")
    return _FALLBACK_DATA_FIELDS


def load_composition_templates() -> list[dict[str, Any]]:
    """Load composition templates from data/knowledge/composition_templates.json or fallback."""
    data_dir = _get_data_dir()
    templates_file = data_dir / "knowledge" / "composition_templates.json"
    templates = _load_json(templates_file)
    if templates and isinstance(templates, list):
        logger.info(f"Loaded {len(templates)} composition templates from {templates_file}")
        return templates
    logger.info("Using built-in fallback composition templates")
    return _FALLBACK_COMPOSITION_TEMPLATES


def load_eval_sets() -> dict[str, list[dict[str, Any]]]:
    """Load evaluation datasets from data/eval/ or fallback."""
    data_dir = _get_data_dir()
    eval_dir = data_dir / "eval"
    result: dict[str, list[dict[str, Any]]] = {}

    eval_files = {
        "intent_eval": "intent_eval.jsonl",
        "tag_eval": "tag_eval.jsonl",
        "topk_eval": "topk_eval.jsonl",
        "explanation_eval": "explanation_eval.jsonl",
    }

    for key, filename in eval_files.items():
        path = eval_dir / filename
        records = _load_jsonl(path)
        if records:
            result[key] = records

    # Also load explanation_survey_mock.json (primary contract per task doc)
    survey_path = eval_dir / "explanation_survey_mock.json"
    survey_data = _load_json(survey_path)
    if survey_data:
        result["explanation_survey"] = survey_data

    if result:
        logger.info(f"Loaded eval sets: { {k: len(v) if isinstance(v, list) else 'dict' for k, v in result.items()} }")
    else:
        logger.info("No eval sets found, using built-in minimal eval set")
        result = _build_fallback_eval_sets()

    return result


def load_official_models() -> list[dict[str, Any]]:
    """Load official models from data/official/model_catalog_structured.jsonl."""
    data_dir = _get_data_dir()
    official_path = data_dir / "official" / "model_catalog_structured.jsonl"
    records = _load_jsonl(official_path)
    if records:
        logger.info(f"Loaded {len(records)} official models from {official_path}")
    else:
        logger.info("No official models found")
    return records


def load_official_eval_sets() -> dict[str, list[dict[str, Any]]]:
    """Load official evaluation datasets from data/eval_official/."""
    data_dir = _get_data_dir()
    eval_official_dir = data_dir / "eval_official"
    result: dict[str, list[dict[str, Any]]] = {}

    if eval_official_dir.exists():
        for fp in sorted(eval_official_dir.glob("*.jsonl")):
            records = _load_jsonl(fp)
            if records:
                result[fp.stem] = records
                logger.info(f"Loaded official eval set '{fp.stem}' ({len(records)} records) from {fp}")
        for fp in sorted(eval_official_dir.glob("*.json")):
            data = _load_json(fp)
            if data is not None:
                if isinstance(data, list):
                    result[fp.stem] = data
                elif isinstance(data, dict):
                    result[fp.stem] = [data]
                logger.info(f"Loaded official eval set '{fp.stem}' from {fp}")

    if not result:
        logger.info("No official eval sets found in data/eval_official/")
    return result


def _build_fallback_eval_sets() -> dict[str, list[dict[str, Any]]]:
    """Build minimal evaluation sets for testing."""
    return {
        "intent_eval": [
            {"demand_id": "EVAL_INT_001", "raw_text": "我想筛一批县域新客做首贷营销给出转化概率高的名单",
             "gold_intent": "customer_marketing", "gold_tags": ["新客", "首贷", "营销转化", "响应预测"]},
            {"demand_id": "EVAL_INT_002", "raw_text": "帮我做农户小额贷款的贷前准入风控识别欺诈风险并给出额度建议",
             "gold_intent": "credit_risk", "gold_tags": ["农户", "小额贷款", "反欺诈", "准入评分", "额度测算"]},
            {"demand_id": "EVAL_INT_003", "raw_text": "我想提前发现对公贷款可能逾期的客户给客户经理一个预警名单",
             "gold_intent": "credit_risk", "gold_tags": ["对公客户", "逾期预测", "贷后预警", "预警名单"]},
            {"demand_id": "EVAL_INT_004", "raw_text": "预测一下这个月的网点客流",
             "gold_intent": "operation_management"},
            {"demand_id": "EVAL_INT_005", "raw_text": "识别小微企业贷款中的欺诈申请",
             "gold_intent": "credit_risk"},
        ],
        "tag_eval": [
            {"demand_id": "EVAL_TAG_001", "raw_text": "县域新客首贷营销转化", "gold_tags": ["新客", "首贷", "营销转化", "响应预测"]},
            {"demand_id": "EVAL_TAG_002", "raw_text": "农户小额贷款贷前反欺诈", "gold_tags": ["农户", "小额贷款", "反欺诈", "涉农贷款"]},
        ],
        "topk_eval": [
            {"demand_id": "EVAL_TOPK_001", "intent": "customer_marketing", "tags": ["新客", "首贷", "营销转化"],
             "gold_model_ids": ["MKT_001", "MKT_005", "MKT_006"]},
            {"demand_id": "EVAL_TOPK_002", "intent": "credit_risk", "tags": ["农户", "反欺诈", "准入评分"],
             "gold_model_ids": ["RISK_001", "RISK_002", "RISK_003"]},
        ],
    }


def build_synonym_map(tags_data: dict[str, Any]) -> dict[str, str]:
    """Build a mapping from any synonym/name to the standard tag key."""
    mapping: dict[str, str] = {}
    for tag in tags_data.get("tags", []):
        key = tag["key"]
        mapping[tag["name"]] = key
        for syn in tag.get("synonyms", []):
            mapping[syn] = key
    return mapping


def get_tag_key_to_name(tags_data: dict[str, Any]) -> dict[str, str]:
    """Build a mapping from tag key to display name."""
    return {tag["key"]: tag["name"] for tag in tags_data.get("tags", [])}
