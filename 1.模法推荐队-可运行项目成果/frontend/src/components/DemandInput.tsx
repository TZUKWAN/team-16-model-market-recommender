import React, { useState } from 'react';

interface DemandInputProps {
  onParse: (text: string) => void;
  loading: boolean;
}

const DEMO_EXAMPLES = [
  {
    id: 'customer_marketing',
    text: '我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。',
    label: '路径1：客户营销',
  },
  {
    id: 'credit_pre_loan',
    text: '帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。',
    label: '路径2：贷前风控',
  },
  {
    id: 'post_loan_early_warning',
    text: '我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。',
    label: '路径3：贷后预警',
  },
];

const DemandInput: React.FC<DemandInputProps> = ({ onParse, loading }) => {
  const [text, setText] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim() && !loading) {
      onParse(text.trim());
    }
  };

  const handleExample = (exampleText: string) => {
    setText(exampleText);
  };

  return (
    <div className="demand-input-section">
      <h2 className="section-title">输入您的业务需求</h2>
      <p className="section-desc">
        用自然语言描述您的业务场景和模型需求，系统将自动解析并推荐最适合的模型。
      </p>

      <div className="demo-examples">
        <span className="examples-label">快速体验：</span>
        {DEMO_EXAMPLES.map((ex) => (
          <button
            key={ex.id}
            className="btn btn-outline btn-sm"
            onClick={() => handleExample(ex.text)}
            disabled={loading}
          >
            {ex.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="demand-form">
        <textarea
          className="demand-textarea"
          placeholder="请描述您的业务需求，例如：我想对存量客户做理财产品的交叉营销，预测客户的购买意向..."
          aria-label="业务需求描述"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          disabled={loading}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!text.trim() || loading}
        >
          {loading ? '解析中...' : '解析需求'}
        </button>
      </form>
    </div>
  );
};

export default DemandInput;
