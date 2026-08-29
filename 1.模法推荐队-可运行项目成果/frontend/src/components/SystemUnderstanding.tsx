import React from 'react';
import type { ParseDemandResponse } from '../types';

interface SystemUnderstandingProps {
  data: ParseDemandResponse;
}

const TagBadge: React.FC<{ tag: string }> = ({ tag }) => (
  <span className="tag-badge">{tag}</span>
);

const parseSourceLabel: Record<string, string> = {
  rule: '规则解析',
  llm: '大模型解析',
  hybrid_fallback: '大模型失败后规则回退',
  error_fallback: '异常兜底',
};

const SystemUnderstanding: React.FC<SystemUnderstandingProps> = ({ data }) => {
  const parseSource = data.parse_source ?? 'rule';

  return (
    <div className="card system-understanding">
      <h3 className="card-title">系统理解</h3>

      <div className="parse-meta-row">
        <span className={`source-pill source-${parseSource}`}>
          {parseSourceLabel[parseSource] ?? parseSource}
        </span>
        <span className="parse-meta-item">
          LLM：{data.llm_enabled ? '已启用' : '未启用'}
        </span>
        {data.llm_trace_id && (
          <span className="parse-meta-item trace-id">
            Trace：{data.llm_trace_id}
          </span>
        )}
      </div>

      <div className="understanding-grid">
        <div className="understanding-item">
          <span className="label">原始需求</span>
          <span className="value">{data.raw_text}</span>
        </div>

        <div className="understanding-item">
          <span className="label">标准化查询</span>
          <span className="value">{data.normalized_query}</span>
        </div>

        <div className="understanding-item">
          <span className="label">意图识别</span>
          <span className="value">{data.intent}</span>
        </div>

        <div className="understanding-item">
          <span className="label">业务领域</span>
          <span className="value">{data.domain}</span>
        </div>

        <div className="understanding-item">
          <span className="label">业务场景</span>
          <span className="value">{data.business_scenario}</span>
        </div>

        <div className="understanding-item">
          <span className="label">业务环节</span>
          <span className="value">{data.business_stage}</span>
        </div>

        {data.customer_segment.length > 0 && (
          <div className="understanding-item">
            <span className="label">目标客群</span>
            <span className="value">{data.customer_segment.join('、')}</span>
          </div>
        )}

        {data.product_type.length > 0 && (
          <div className="understanding-item">
            <span className="label">产品类型</span>
            <span className="value">{data.product_type.join('、')}</span>
          </div>
        )}

        {data.risk_type.length > 0 && (
          <div className="understanding-item">
            <span className="label">风险类型</span>
            <span className="value">{data.risk_type.join('、')}</span>
          </div>
        )}

        <div className="understanding-item">
          <span className="label">期望输出</span>
          <span className="value">{data.expected_outputs.join('、')}</span>
        </div>

        {data.data_conditions.length > 0 && (
          <div className="understanding-item">
            <span className="label">数据条件</span>
            <span className="value">{data.data_conditions.join('、')}</span>
          </div>
        )}

        {data.constraints.length > 0 && (
          <div className="understanding-item">
            <span className="label">约束条件</span>
            <span className="value">{data.constraints.join('；')}</span>
          </div>
        )}
      </div>

      <div className="tags-section">
        <span className="label">需求标签</span>
        <div className="tags-list">
          {(() => {
            const displayTags =
              data.tag_names?.length ? data.tag_names : data.tags;
            return displayTags.map((tag) => <TagBadge key={tag} tag={tag} />);
          })()}
        </div>
      </div>

      {Object.keys(data.structured_filters).length > 0 && (
        <div className="filters-section">
          <span className="label">结构化过滤器</span>
          <pre className="filter-json">{JSON.stringify(data.structured_filters, null, 2)}</pre>
        </div>
      )}

      <div className="translation-section">
        <span className="label">业务语言 → 模型语言 翻译</span>
        <p className="translation-text">{data.business_to_model_translation}</p>
      </div>

      <div className="summary-section">
        <span className="label">用户确认摘要</span>
        <p className="summary-text">{data.user_confirmable_summary}</p>
      </div>
    </div>
  );
};

export default SystemUnderstanding;
