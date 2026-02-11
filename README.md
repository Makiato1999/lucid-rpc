# Lucid RPC (Iterating)

这个仓库实现了一个**正在持续迭代的 Python RPC**，当前以简单、可读、可验证为核心，便于快速扩展与实验。

当前实现基础：

- TCP sockets
- JSON 消息
- 4-byte length prefix 消息分帧

## 项目结构

- `rpc.py`：RPC client/server 核心实现
- `examples/server.py`：示例服务端（含 `add`、`divide`）
- `examples/client.py`：示例客户端调用

## 快速运行

启动服务端：

```bash
python3 -m examples.server
```

另开一个终端运行客户端：

```bash
python3 -m examples.client
```

你会看到 `add`、`divide` 的正常结果，以及 `divide(10, 0)` 的错误返回。

## Roadmap（迭代摘要）

按优先级从近到远：

1. **请求/响应标准化**
   - 引入 `request_id`、统一 `ok/result/error` 结构、标准 `meta`
   - 支持单连接多请求并发（multiplexing）
2. **可靠性增强**
   - timeout + retry（指数退避）
   - 结合幂等信息控制重试策略
3. **协议治理**
   - 参数与协议校验
   - 标准错误码体系（如 `BAD_REQUEST`、`TIMEOUT`、`INTERNAL`）
4. **并发模型升级**
   - 增加 asyncio 版本，保留现有实现作为稳定基线
5. **可运维能力**
   - 优雅下线（drain in-flight）
   - 心跳与空闲连接回收
   - 结构化日志与可观测性指标
6. **容量与演进能力**
   - 背压与并发限制
   - 批量请求与压缩
   - 协议版本化、二进制协议、IDL 代码生成

> 目标：从“可用的最小 RPC”平滑演进到“可治理、可扩展、可观测”的工程化 RPC。
