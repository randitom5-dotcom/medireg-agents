import { CloudServerOutlined, DatabaseOutlined, FileSearchOutlined } from "@ant-design/icons";

const agents = [
  {
    icon: <CloudServerOutlined aria-hidden />,
    name: "网络搜索助手",
    detail: "公开监管网页、政策公告、最新动态和外部来源核验"
  },
  {
    icon: <DatabaseOutlined aria-hidden />,
    name: "数据库查询助手",
    detail: "MySQL 注册证、批准产品公告、临床评价路径和结构化表格查询"
  },
  {
    icon: <FileSearchOutlined aria-hidden />,
    name: "RAGFlow 助手",
    detail: "指导原则、审评报告、共性问题、工作区资料和上传文件问答"
  }
];

export function AgentTopology() {
  return (
    <section className="console-panel topology-panel" aria-labelledby="topology-title">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">ROUTING MAP</span>
          <h2 id="topology-title">注册知识检索路由</h2>
        </div>
      </div>
      <div className="agent-hub">
        <div className="main-agent-node">
          <span>MAIN</span>
          <strong>注册问答主智能体</strong>
        </div>
        <div className="agent-links" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div className="agent-node-list">
          {agents.map((agent) => (
            <div className="agent-node" key={agent.name}>
              <div className="agent-node-icon">{agent.icon}</div>
              <div>
                <strong>{agent.name}</strong>
                <p>{agent.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
