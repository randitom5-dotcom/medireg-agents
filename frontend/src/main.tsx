import "antd/dist/reset.css";
import { App as AntApp, ConfigProvider, theme } from "antd";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#0f7f86",
          colorSuccess: "#2f8f5b",
          colorWarning: "#b7791f",
          colorError: "#c2414b",
          colorInfo: "#2563a8",
          colorBgBase: "#f5f8fb",
          colorBgContainer: "#ffffff",
          colorBorder: "#d9e4ea",
          colorTextBase: "#1d2b36",
          borderRadius: 8,
          fontFamily:
            "'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
          fontFamilyCode:
            "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
        },
        components: {
          Button: {
            controlHeightLG: 46,
            primaryShadow: "0 8px 20px rgba(15, 127, 134, 0.18)"
          },
          Input: {
            activeBorderColor: "#0f7f86",
            hoverBorderColor: "#2f8f5b"
          }
        }
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
