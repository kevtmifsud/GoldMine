import { TOOL_CATEGORIES, CATEGORY_SLUGS } from "../../hooks/useSlashCommand";
import type { SlashCommandState, SlashCommandActions } from "../../hooks/useSlashCommand";

interface SlashMenuProps {
  slash: SlashCommandState & SlashCommandActions;
  onSelectCategory: (slug: string) => void;
  onSelectTool: (toolName: string) => void;
  onSelectEnumValue: (value: string) => void;
  onSendPrompt: (prompt: string) => void;
  onDismiss: () => void;
}

export function SlashMenu({
  slash,
  onSelectCategory,
  onSelectTool,
  onSelectEnumValue,
  onDismiss,
}: SlashMenuProps) {
  // ── Category picker ──
  if (slash.menuMode === "categories") {
    const partial = slash.slashCategory?.toLowerCase() ?? "";
    const filtered = CATEGORY_SLUGS.filter((s) => s.startsWith(partial));

    if (slash.loading) {
      return (
        <div className="slash-menu">
          <div className="slash-menu__loading">Loading...</div>
        </div>
      );
    }

    return (
      <div className="slash-menu">
        <div className="slash-menu__header">
          <span className="slash-menu__header-label">Commands</span>
          <button className="slash-menu__dismiss" onClick={onDismiss}>Esc</button>
        </div>
        <div className="slash-menu__list" role="listbox">
          {filtered.reduce<{ slug: string; cat: typeof TOOL_CATEGORIES[string]; count: number }[]>(
            (acc, slug) => {
              const cat = TOOL_CATEGORIES[slug];
              const count = cat.tools.filter((n) => slash.allTools.some((t) => t.name === n)).length;
              if (count > 0) acc.push({ slug, cat, count });
              return acc;
            }, [],
          ).map(({ slug, cat, count }, idx) => (
            <div
              key={slug}
              className={`slash-menu__item${idx === slash.selectedIndex ? " slash-menu__item--selected" : ""}`}
              role="option"
              aria-selected={idx === slash.selectedIndex}
              onClick={() => onSelectCategory(slug)}
            >
              <div className="slash-menu__item-content">
                <span className="slash-menu__item-name">{cat.display}</span>
                <span className="slash-menu__item-desc">{cat.description}</span>
              </div>
              <span className="slash-menu__item-badge">
                {count} {count === 1 ? "tool" : "tools"}
              </span>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="slash-menu__empty">No matching categories</div>
          )}
        </div>
      </div>
    );
  }

  // ── Tool picker within category ──
  if (slash.menuMode === "tools") {
    const partial = slash.slashToolName?.toLowerCase() ?? "";
    const filtered = slash.categoryTools.filter((t) =>
      t.name.toLowerCase().startsWith(partial),
    );
    const catDisplay = TOOL_CATEGORIES[slash.slashCategory ?? ""]?.display ?? slash.slashCategory;

    return (
      <div className="slash-menu">
        <div className="slash-menu__header">
          <span className="slash-menu__header-label">{catDisplay}</span>
          <button className="slash-menu__dismiss" onClick={onDismiss}>Esc</button>
        </div>
        <div className="slash-menu__list" role="listbox">
          {filtered.map((tool, idx) => (
            <div
              key={tool.name}
              className={`slash-menu__item${idx === slash.selectedIndex ? " slash-menu__item--selected" : ""}`}
              role="option"
              aria-selected={idx === slash.selectedIndex}
              onClick={() => onSelectTool(tool.name)}
            >
              <div className="slash-menu__item-content">
                <span className="slash-menu__item-name slash-menu__item-name--mono">
                  {tool.name}
                </span>
                <span className="slash-menu__item-desc">{tool.description}</span>
              </div>
              <span className="slash-menu__item-params-hint">
                {tool.parameters
                  .filter((p) => p.required)
                  .map((p) => `<${p.name}>`)
                  .join(" ")}
              </span>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="slash-menu__empty">No matching tools</div>
          )}
        </div>
      </div>
    );
  }

  // ── Inline param hints (Excel-style) ──
  if (slash.menuMode === "params" && slash.selectedTool) {
    const tool = slash.selectedTool;
    const currentParam = tool.parameters[slash.currentParamIndex];
    const hasEnum = currentParam?.enum && currentParam.enum.length > 0;

    return (
      <div className="slash-menu slash-menu--params">
        {/* Function signature bar */}
        <div className="slash-param-sig">
          <span className="slash-param-sig__name">{tool.name}(</span>
          {tool.parameters.map((p, i) => {
            const filled = (slash.slashParams[i] ?? "").trim();
            const isCurrent = i === slash.currentParamIndex;
            const isPast = i < slash.currentParamIndex || (i < slash.slashParams.length && !isCurrent);
            const isMissing = p.required && !filled;
            return (
              <span key={p.name}>
                {i > 0 && <span className="slash-param-sig__comma">, </span>}
                <span
                  className={
                    `slash-param-sig__param` +
                    (isCurrent ? " slash-param-sig__param--active" : "") +
                    (isPast && filled ? " slash-param-sig__param--filled" : "") +
                    (isPast && isMissing ? " slash-param-sig__param--missing" : "")
                  }
                >
                  {filled && isPast ? filled : p.name}
                  {p.required && <span className="slash-param-sig__req">{filled ? "" : "*"}</span>}
                </span>
              </span>
            );
          })}
          <span className="slash-param-sig__name">)</span>
          <button className="slash-menu__dismiss" onClick={onDismiss}>Esc</button>
        </div>

        {/* Current param detail + enum options */}
        {currentParam && (
          <div className="slash-param-detail">
            <span className="slash-param-detail__label">
              {currentParam.name}
              {currentParam.required && <span className="slash-param-detail__req"> (required)</span>}
              {!currentParam.required && <span className="slash-param-detail__opt"> (optional — Tab to skip)</span>}
            </span>
            <span className="slash-param-detail__type">{currentParam.type}</span>
            <span className="slash-param-detail__desc">{currentParam.description}</span>
          </div>
        )}

        {/* Enum options as selectable chips */}
        {hasEnum && (
          <div className="slash-param-enum" role="listbox">
            {currentParam!.enum!.map((val, idx) => (
              <button
                key={val}
                className={`slash-param-enum__item${idx === slash.selectedIndex ? " slash-param-enum__item--selected" : ""}`}
                role="option"
                aria-selected={idx === slash.selectedIndex}
                onClick={() => onSelectEnumValue(val)}
              >
                {val}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return null;
}
