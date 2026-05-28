import { PlayCircleOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";

const { TextArea } = Input;

const presets = [
  "检索医疗器械临床评价路径相关依据，并整理同品种比对和临床试验适用条件。",
  "结合 RAGFlow 指导原则和共性问题，整理某类产品注册申报资料缺口分析报告。",
  "查询数据库中的注册证和批准产品公告，分析同类产品注册情况并输出结论。"
];

interface MissionComposerProps {
  query: string;
  isRunning: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
}

export function MissionComposer({
  query,
  isRunning,
  onQueryChange,
  onSubmit
}: MissionComposerProps) {
  return (
    <section className="console-panel composer-panel" aria-labelledby="composer-title">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">MEDIREG TASK</span>
          <h2 id="composer-title">发起注册分析</h2>
        </div>
        <ThunderboltOutlined className="panel-heading-icon" aria-hidden />
      </div>

      <TextArea
        aria-label="注册知识库任务"
        className="mission-textarea"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="输入要交给 MediReg Agents 的任务，例如：查询某类产品临床评价路径，并生成带引用来源的 Markdown 报告。"
        autoSize={{ minRows: 7, maxRows: 12 }}
        disabled={isRunning}
      />

      <div className="preset-grid" aria-label="注册任务模板">
        {presets.map((preset) => (
          <button
            className="preset-chip"
            type="button"
            key={preset}
            onClick={() => onQueryChange(preset)}
            disabled={isRunning}
          >
            {preset}
          </button>
        ))}
      </div>

      <Button
        block
        className="launch-button"
        disabled={isRunning}
        icon={<PlayCircleOutlined />}
        loading={isRunning}
        onClick={onSubmit}
        size="large"
        type="primary"
      >
        {isRunning ? "任务执行中" : "启动注册分析"}
      </Button>
    </section>
  );
}
