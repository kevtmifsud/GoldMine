from __future__ import annotations

from typing import Any

import anthropic

from app.config.settings import settings
from app.exceptions import GoldMineError
from app.llm.studio_tools import STUDIO_TOOLS, execute_tool
from app.logging_config import get_logger
from app.studios.models import ChatMessage, StudioWidget

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
You are a data visualization assistant for the GoldMine investment research platform.
Your role is to help users explore financial data by creating charts on a canvas.

## Tools

**Chart creation** (use these first):
- create_echarts_chart — create ANY chart type. Pass data_sources to let the server fetch data — DO NOT embed large datasets in echarts_option.
- remove_chart — remove a chart from the canvas

**Data preview** (only use when you need to explore what data is available):
- list_available_data — discover datasets and financial data sources
- query_dataset — preview rows from a CSV dataset
- get_financial_data — preview financial statement data (NOT needed before charting — use data_sources instead)
- get_price_history — preview daily closing prices (NOT needed before charting — use data_sources instead)

## Workflow — IMPORTANT

**For ANY chart involving stock prices or financial data:**
Call create_echarts_chart in a SINGLE tool call with data_sources. The server resolves the data and injects it automatically.
DO NOT call get_price_history or get_financial_data first — data_sources handles this server-side with zero token cost.
DO NOT try to embed price or financial data inline in echarts_option — use data_sources.

**For other charts** (pie, gauge, small custom datasets):
Query data first with preview tools, then embed the small dataset directly in echarts_option.

To modify a chart: remove_chart the old one, then create_echarts_chart a new one.

## ECharts patterns with data_sources

**Single-series line** (e.g. AAPL stock price from 2023):
echarts_option: { xAxis: { type: 'category' }, yAxis: { type: 'value' }, series: [{ name: 'AAPL', type: 'line', showSymbol: false }] }
data_sources: [{ type: 'price_history', ticker: 'AAPL', start_date: '2023-01-01' }]

**Multi-series line** (e.g. Mag 7 indexed returns from 2023):
echarts_option: { xAxis: { type: 'category' }, yAxis: {}, legend: {}, series: [{ name: 'AAPL', type: 'line', showSymbol: false }, { name: 'MSFT', type: 'line', showSymbol: false }, ...] }
data_sources: [{ type: 'price_history', ticker: 'AAPL', start_date: '2023-01-01' }, { type: 'price_history', ticker: 'MSFT', start_date: '2023-01-01' }, ...]
indexed: true (for relative performance comparison, base=100)

**Single-series bar** (e.g. AAPL annual revenue):
echarts_option: { xAxis: { type: 'category' }, yAxis: { type: 'value', axisLabel: { formatter: '${value}' } }, series: [{ name: 'AAPL', type: 'bar', color: '#3182ce' }] }
data_sources: [{ type: 'financials', ticker: 'AAPL', statement_type: 'income_statement', metric: 'total_revenue' }]

**Multi-series bar** (e.g. comparing EPS across tickers):
echarts_option: { xAxis: { type: 'category' }, yAxis: {}, legend: {}, series: [{ name: 'AAPL', type: 'bar' }, { name: 'MSFT', type: 'bar' }] }
data_sources: [{ type: 'financials', ticker: 'AAPL', statement_type: 'income_statement', metric: 'diluted_eps' }, { type: 'financials', ticker: 'MSFT', statement_type: 'income_statement', metric: 'diluted_eps' }]

## ECharts patterns with inline data

**Pie chart** (e.g. revenue breakdown — query data first, then embed):
{ series: [{ type: 'pie', radius: '60%', data: [{ value: 100, name: 'Product A' }, ...] }] }

**Scatter, candlestick, gauge, radar**: see create_echarts_chart tool description for patterns.

## Guidelines

- Use descriptive titles (e.g. "AAPL Annual Revenue" not "Chart 1")
- Format dollar values with axisLabel formatter (e.g. '${value}') or tooltip valueFormatter
- Use color palette: #3182ce, #e53e3e, #38a169, #d69e2e, #805ad5, #dd6b20, #319795
- For multi-series: assign one color per series, add legend
- Keep text responses concise — the charts speak for themselves
- When the user asks to show data, create a chart immediately — use data_sources so you don't need to query first
- When asked to modify or remove charts, reference them by widget_id from the canvas state
- Well-known stock groups: Mag 7 = AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA; FAANG = META, AAPL, AMZN, NFLX, GOOGL
"""


class StudioLLMProvider:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def chat(
        self,
        user_message: str,
        conversation_history: list[ChatMessage],
        widgets: list[StudioWidget],
        row_columns: list[int],
    ) -> tuple[str, list[StudioWidget], list[int], str, dict[str, int]]:
        """
        Run a tool-calling conversation loop.
        Returns (reply_text, updated_widgets, updated_row_columns, model, token_usage).
        """
        # Build canvas state description for context
        canvas_desc = self._build_canvas_description(widgets)

        # Build messages array
        messages: list[dict[str, Any]] = []

        # Replay prior conversation (simplified — text only)
        for msg in conversation_history:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})

        # Don't duplicate — the last message in conversation_history IS the user message
        # if conversation_history is provided. But the caller appends the user msg to history,
        # so the current user_message may or may not be in there.
        # We always build with the history that's passed, and don't add user_message again
        # since the caller includes it in conversation_history.

        # If messages is empty or last message is not from user, add the user message
        if not messages or messages[-1]["role"] != "user":
            content = user_message
            if canvas_desc:
                content = f"[Current canvas state]\n{canvas_desc}\n\n{user_message}"
            messages.append({"role": "user", "content": content})
        else:
            # Inject canvas state into the last user message
            if canvas_desc:
                last_content = messages[-1]["content"]
                messages[-1]["content"] = f"[Current canvas state]\n{canvas_desc}\n\n{last_content}"

        total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        model_name = ""

        try:
            response = self._client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=STUDIO_TOOLS,
                timeout=120,
            )

            model_name = response.model
            if response.usage:
                total_usage["input_tokens"] += response.usage.input_tokens
                total_usage["output_tokens"] += response.usage.output_tokens

            # Tool-calling loop
            while response.stop_reason == "tool_use":
                # Process tool calls
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        result_text = execute_tool(
                            block.name, block.input, widgets, row_columns
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result_text),
                        })

                # Continue conversation
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                response = self._client.messages.create(
                    model=settings.LLM_MODEL,
                    max_tokens=8192,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=STUDIO_TOOLS,
                    timeout=120,
                )

                if response.usage:
                    total_usage["input_tokens"] += response.usage.input_tokens
                    total_usage["output_tokens"] += response.usage.output_tokens

            # Extract final text reply
            reply = ""
            for block in response.content:
                if block.type == "text":
                    reply += block.text

            return reply, widgets, row_columns, model_name, total_usage

        except anthropic.BadRequestError as e:
            if "credit balance" in str(e).lower():
                raise GoldMineError(
                    "Anthropic API credit balance too low.",
                    status_code=402,
                )
            raise GoldMineError(f"Invalid request: {e}", status_code=400)
        except anthropic.AuthenticationError:
            raise GoldMineError(
                "Invalid Anthropic API key.", status_code=401
            )
        except anthropic.RateLimitError:
            raise GoldMineError("Rate limited", status_code=429)
        except anthropic.APITimeoutError:
            raise GoldMineError("LLM request timed out", status_code=504)
        except anthropic.APIError as e:
            raise GoldMineError(f"LLM service error: {e}", status_code=502)

    @staticmethod
    def _build_canvas_description(widgets: list[StudioWidget]) -> str:
        """Build a text description of the current canvas state for the LLM."""
        if not widgets:
            return "Canvas is empty — no charts yet."

        lines = [f"Canvas has {len(widgets)} chart(s):"]
        for w in widgets:
            if w.chart_type == "echarts" and w.echarts_option:
                # Summarize series types from the echarts option
                series = w.echarts_option.get("series", [])
                if isinstance(series, list) and series:
                    types = {s.get("type", "unknown") for s in series if isinstance(s, dict)}
                    type_str = ", ".join(sorted(types))
                else:
                    type_str = "custom"
                lines.append(
                    f"- widget_id={w.widget_id}, title=\"{w.title}\", "
                    f"type=echarts ({type_str}), position=row {w.row + 1} col {w.col + 1} "
                    f"(raw echarts option — use remove_chart to replace)"
                )
            else:
                lines.append(
                    f"- widget_id={w.widget_id}, title=\"{w.title}\", "
                    f"type={w.chart_type}, position=row {w.row + 1} col {w.col + 1}, "
                    f"data_source={w.data_source.type}"
                    + (f" (ticker={w.data_source.ticker})" if w.data_source.ticker else "")
                    + (f" (dataset={w.data_source.dataset})" if w.data_source.dataset else "")
                )
        return "\n".join(lines)
