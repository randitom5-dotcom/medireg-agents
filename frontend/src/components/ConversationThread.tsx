import {
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  FileMarkdownOutlined,
  FilePdfOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  StopOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import { useEffect, useRef, useState } from "react";
import { getDownloadUrl } from "../lib/api";
import { MarkdownRenderer } from "./MarkdownRenderer";
import type { MonitorMessage, OutputFile } from "../types";

export interface ChatTurn {
  id: string;
  content: string;
  events: MonitorMessage[];
  files: OutputFile[];
  isRunning: boolean;
  result: string;
  timestamp: string;
}

interface ConversationThreadProps {
  onUseExample: (prompt: string) => void;
  turns: ChatTurn[];
}

const TASK_EXAMPLES = [
  {
    tool: "监管公开信息",
    title: "查询注册证信息",
    prompt: "查询南京鼎世医疗器械有限公司相关医疗器械注册信息，并列出产品名称、注册证编号和有效期。",
    icon: <CloudServerOutlined aria-hidden />,
  },
  {
    tool: "结构化数据库",
    title: "按企业检索产品",
    prompt: "检索南京鼎世医疗器械有限公司的硅橡胶相关产品注册记录，按注册证编号整理结果。",
    icon: <DatabaseOutlined aria-hidden />,
  },
  {
    tool: "RAGFlow 知识库",
    title: "检索法规依据",
    prompt: "检索医疗器械临床评价路径相关法规和指导原则，给出出处和适用场景。",
    icon: <FileSearchOutlined aria-hidden />,
  },
  {
    tool: "报告生成",
    title: "生成判断要点",
    prompt: "生成一份《医疗器械临床评价路径判断要点》的 Markdown 报告，要求包含适用场景、判断步骤、资料清单和风险提示。",
    icon: <FileTextOutlined aria-hidden />,
  },
  {
    tool: "Markdown/PDF",
    title: "输出可追溯报告",
    prompt: "基于检索到的法规和注册信息，生成一份带引用来源的 Markdown 报告，并列出证据缺口。",
    icon: <FileMarkdownOutlined aria-hidden />,
  },
];

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return date.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function parseTime(value: string): number | null {
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function formatDuration(value: number): string {
  const totalSeconds = Math.max(0, Math.floor(value / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const paddedMinutes = String(minutes).padStart(2, "0");
  const paddedSeconds = String(seconds).padStart(2, "0");

  if (hours > 0) {
    return `${hours}:${paddedMinutes}:${paddedSeconds}`;
  }
  return `${paddedMinutes}:${paddedSeconds}`;
}

function getLastEventTime(
  events: MonitorMessage[],
  eventName?: string,
): number | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (!eventName || event.event === eventName) {
      return parseTime(event.timestamp);
    }
  }
  return null;
}

function getThinkingDuration(
  events: MonitorMessage[],
  fallbackStart: string,
  isRunning: boolean,
  now: number,
): string {
  const startedAt =
    (events[0] ? parseTime(events[0].timestamp) : null) ??
    parseTime(fallbackStart) ??
    now;
  const finishedAt =
    getLastEventTime(events, "task_result") ??
    (!isRunning ? getLastEventTime(events) : null) ??
    now;
  return formatDuration(finishedAt - startedAt);
}

function EventIcon({ event }: { event: string }) {
  if (event === "assistant_call") {
    return <BranchesOutlined aria-hidden />;
  }
  if (event === "tool_start") {
    return <ToolOutlined aria-hidden />;
  }
  if (event === "session_created") {
    return <FileSearchOutlined aria-hidden />;
  }
  if (event === "task_result") {
    return <CheckCircleOutlined aria-hidden />;
  }
  if (event === "task_cancelled") {
    return <StopOutlined aria-hidden />;
  }
  if (event === "error") {
    return <CloseCircleOutlined aria-hidden />;
  }
  return <ClockCircleOutlined aria-hidden />;
}

function FileIcon({ name }: { name: string }) {
  if (name.endsWith(".pdf")) {
    return <FilePdfOutlined aria-hidden />;
  }
  if (name.endsWith(".md")) {
    return <FileMarkdownOutlined aria-hidden />;
  }
  return <FileTextOutlined aria-hidden />;
}

function ThinkingTimeline({ events }: { events: MonitorMessage[] }) {
  const timelineRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => {
    const timelineNode = timelineRef.current;
    if (!timelineNode) {
      return;
    }

    window.requestAnimationFrame(() => {
      timelineNode.scrollTop = timelineNode.scrollHeight;
    });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="thinking-empty">
        <ClockCircleOutlined aria-hidden />
        等待后端推送执行事件
      </div>
    );
  }

  return (
    <ol className="thinking-timeline" ref={timelineRef}>
      {events.map((event, index) => (
        <li
          className={`thinking-event thinking-event--${event.event}`}
          key={`${event.timestamp}-${index}`}
        >
          <span className="thinking-event-icon">
            <EventIcon event={event.event} />
          </span>
          <div>
            <div className="thinking-event-meta">
              <span>{event.event}</span>
              <time dateTime={event.timestamp}>
                {formatTime(event.timestamp)}
              </time>
            </div>
            <p>{event.message}</p>
            {event.event === "assistant_call" ||
            event.event === "tool_start" ? (
              <code>{JSON.stringify(event.data)}</code>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

function ArtifactShelf({ files }: { files: OutputFile[] }) {
  if (files.length === 0) {
    return (
      <div className="artifact-empty">
        <FileSearchOutlined aria-hidden />
        {noOutputFilesLabel}
      </div>
    );
  }

  return (
    <div className="artifact-shelf">
      {files.map((file) => (
        <div className="artifact-card" key={file.path}>
          <span className="artifact-icon">
            <FileIcon name={file.name} />
          </span>
          <div className="artifact-copy">
            <strong title={file.name}>{file.name}</strong>
            <span>{formatBytes(file.size)}</span>
          </div>
          <Tooltip title={downloadLabel}>
            <Button
              aria-label={`${downloadLabel} ${file.name}`}
              className="artifact-download"
              href={getDownloadUrl(file.path)}
              icon={<DownloadOutlined />}
              shape="circle"
            />
          </Tooltip>
        </div>
      ))}
    </div>
  );
}
function getLoaderStep(events: MonitorMessage[]): number {
  if (events.some((event) => event.event === "task_result")) {
    return 2;
  }

  if (events.some((event) => event.event === "tool_start" || event.event === "assistant_call")) {
    return 1;
  }

  return 0;
}

const loaderLabels = ["\u7406\u89e3\u95ee\u9898", "\u68c0\u7d22\u5206\u6790", "\u6574\u7406\u7ed3\u8bba"];
const loadingStatusLabel = "\u6b63\u5728\u5206\u6790";
const thinkingTimeLabel = "\u5df2\u601d\u8003";
const cancelledLabel = "\u5df2\u53d6\u6d88";
const syncedLabel = "\u5df2\u540c\u6b65";
const elapsedLabel = "\u7528\u65f6";
const thinkingAriaLabel = "\u6b63\u5728\u5206\u6790\u4efb\u52a1";
const processTitle = "\u68c0\u7d22\u4e0e\u5206\u6790\u8fc7\u7a0b";
const finalPlaceholder = "\u4efb\u52a1\u5b8c\u6210\u540e\u4f1a\u5728\u8fd9\u91cc\u663e\u793a\u6700\u7ec8\u56de\u590d\u3002";
const outputFilesTitle = "\u8f93\u51fa\u6587\u4ef6";
const noOutputFilesLabel = "\u6682\u65e0\u8f93\u51fa\u6587\u4ef6";
const downloadLabel = "\u4e0b\u8f7d";
const separatorLabel = "\u00b7";

function ThinkingLoader({
  durationLabel,
  events,
}: {
  durationLabel: string;
  events: MonitorMessage[];
}) {
  const activeStep = getLoaderStep(events);

  return (
    <div className="thinking-loader" aria-live="polite" aria-label={thinkingAriaLabel}>
      <div className="loader-status">
        <span className="loader-pulse" aria-hidden />
        <strong>{loadingStatusLabel}</strong>
        <span className="loader-duration">
          {thinkingTimeLabel} {durationLabel}
        </span>
        <span className="loader-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
      </div>
      <div className="loader-track" aria-hidden />
      <ul className="loader-steps" aria-hidden>
        {loaderLabels.map((label, index) => (
          <li className={index === activeStep ? "loader-step--active" : ""} key={label}>
            {label}
          </li>
        ))}
      </ul>
    </div>
  );
}
function AssistantMessage({
  events,
  files,
  isRunning,
  result,
  timestamp,
}: Pick<ChatTurn, "events" | "files" | "isRunning" | "result" | "timestamp">) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!isRunning) {
      return;
    }

    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [isRunning]);

  const durationLabel = getThinkingDuration(events, timestamp, isRunning, now);
  const isCancelled = events.some((event) => event.event === "task_cancelled");
  const syncLabel = isRunning
    ? `${loadingStatusLabel} ${separatorLabel} ${thinkingTimeLabel} ${durationLabel}`
    : `${isCancelled ? cancelledLabel : syncedLabel} ${separatorLabel} ${elapsedLabel} ${durationLabel}`;

  return (
    <article className="chat-message chat-message--assistant">
      <div className="message-avatar">AI</div>
      <div className="message-bubble">
        <div className="message-meta">
          <span>MediReg Agents</span>
          <time>{syncLabel}</time>
        </div>

        <details className="thinking-block" open={isRunning || events.length > 0}>
          <summary>
            <span>
              <BranchesOutlined aria-hidden />
              {processTitle}
            </span>
            <strong>{events.length}</strong>
          </summary>
          <ThinkingTimeline events={events} />
        </details>

        {result ? (
          <div className="assistant-answer">
            <MarkdownRenderer content={result} />
          </div>
        ) : (
          <div className="assistant-answer assistant-answer--pending">
            {isRunning ? (
              <ThinkingLoader durationLabel={durationLabel} events={events} />
            ) : (
              finalPlaceholder
            )}
          </div>
        )}

        <details className="thinking-block artifact-block" open={files.length > 0}>
          <summary>
            <span>
              <FileSearchOutlined aria-hidden />
              {outputFilesTitle}
            </span>
            <strong>{files.length}</strong>
          </summary>
          <ArtifactShelf files={files} />
        </details>
      </div>
    </article>
  );
}
export function ConversationThread({
  onUseExample,
  turns,
}: ConversationThreadProps) {
  if (turns.length === 0) {
    return (
      <div className="conversation-empty">
        <div className="empty-examples">
          <div className="empty-examples-copy">
            <span className="panel-kicker">TASK EXAMPLES</span>
            <h3>选择一个注册知识库任务开始</h3>
            <p>可检索监管公开信息、结构化注册数据和知识库资料，并生成可追溯的分析报告。</p>
          </div>

          <div className="example-grid" aria-label="医疗器械注册知识库任务示例">
            {TASK_EXAMPLES.map((example) => (
              <button
                className="example-card"
                key={example.tool}
                onClick={() => onUseExample(example.prompt)}
                type="button"
              >
                <span className="example-icon">{example.icon}</span>
                <span className="example-copy">
                  <span>{example.tool}</span>
                  <strong>{example.title}</strong>
                  <small>{example.prompt}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="conversation-thread" aria-label="聊天消息流">
      {turns.map((turn) => (
        <div className="conversation-turn" key={turn.id}>
          <article className="chat-message chat-message--user">
            <div className="message-bubble">
              <div className="message-meta">
                <span>你</span>
                <time dateTime={turn.timestamp}>{formatTime(turn.timestamp)}</time>
              </div>
              <p>{turn.content}</p>
            </div>
          </article>

          <AssistantMessage
            events={turn.events}
            files={turn.files}
            isRunning={turn.isRunning}
            result={turn.result}
            timestamp={turn.timestamp}
          />
        </div>
      ))}
    </div>
  );
}




