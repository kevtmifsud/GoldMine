// ---------------------------------------------------------------------------
// Formula Engine — tokenizer, recursive-descent parser, and AST evaluator.
// Pure TypeScript, no external dependencies.
// ---------------------------------------------------------------------------

// ---- Error class ----

export class FormulaError extends Error {
  position: number;
  constructor(message: string, position: number) {
    super(message);
    this.name = "FormulaError";
    this.position = position;
  }
}

// ---- Token types ----

type TokenType =
  | "NUMBER"
  | "STRING"
  | "FIELD"
  | "LPAREN"
  | "RPAREN"
  | "LBRACKET"
  | "RBRACKET"
  | "COMMA"
  | "PLUS"
  | "MINUS"
  | "STAR"
  | "SLASH"
  | "EQ"
  | "NEQ"
  | "LTE"
  | "GTE"
  | "LT"
  | "GT"
  | "IF"
  | "THEN"
  | "ELSE"
  | "IN"
  | "EOF";

interface Token {
  type: TokenType;
  value: string;
  pos: number;
}

// ---- AST node types ----

export type ASTNode =
  | { type: "number"; value: number }
  | { type: "string"; value: string }
  | { type: "field"; name: string }
  | { type: "unary"; op: "-"; operand: ASTNode }
  | { type: "binary"; op: "+" | "-" | "*" | "/"; left: ASTNode; right: ASTNode }
  | { type: "comparison"; op: "=" | "!=" | "<" | ">" | "<=" | ">="; left: ASTNode; right: ASTNode }
  | { type: "in"; value: ASTNode; list: ASTNode[] }
  | { type: "conditional"; condition: ASTNode; then: ASTNode; else: ASTNode };

// ---- Tokenizer ----

const KEYWORDS: Record<string, TokenType> = {
  IF: "IF",
  THEN: "THEN",
  ELSE: "ELSE",
  IN: "IN",
};

function tokenize(input: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < input.length) {
    // Skip whitespace
    if (/\s/.test(input[i])) {
      i++;
      continue;
    }

    const pos = i;
    const ch = input[i];

    // Single-char tokens
    if (ch === "(") { tokens.push({ type: "LPAREN", value: "(", pos }); i++; continue; }
    if (ch === ")") { tokens.push({ type: "RPAREN", value: ")", pos }); i++; continue; }
    if (ch === "[") { tokens.push({ type: "LBRACKET", value: "[", pos }); i++; continue; }
    if (ch === "]") { tokens.push({ type: "RBRACKET", value: "]", pos }); i++; continue; }
    if (ch === ",") { tokens.push({ type: "COMMA", value: ",", pos }); i++; continue; }
    if (ch === "+") { tokens.push({ type: "PLUS", value: "+", pos }); i++; continue; }
    if (ch === "-") { tokens.push({ type: "MINUS", value: "-", pos }); i++; continue; }
    if (ch === "*") { tokens.push({ type: "STAR", value: "*", pos }); i++; continue; }
    if (ch === "/") { tokens.push({ type: "SLASH", value: "/", pos }); i++; continue; }

    // Two-char comparison operators
    if (ch === "!" && input[i + 1] === "=") {
      tokens.push({ type: "NEQ", value: "!=", pos }); i += 2; continue;
    }
    if (ch === "<" && input[i + 1] === "=") {
      tokens.push({ type: "LTE", value: "<=", pos }); i += 2; continue;
    }
    if (ch === ">" && input[i + 1] === "=") {
      tokens.push({ type: "GTE", value: ">=", pos }); i += 2; continue;
    }
    if (ch === "=") { tokens.push({ type: "EQ", value: "=", pos }); i++; continue; }
    if (ch === "<") { tokens.push({ type: "LT", value: "<", pos }); i++; continue; }
    if (ch === ">") { tokens.push({ type: "GT", value: ">", pos }); i++; continue; }

    // Number literal
    if (/[0-9]/.test(ch) || (ch === "." && i + 1 < input.length && /[0-9]/.test(input[i + 1]))) {
      let num = "";
      while (i < input.length && /[0-9.]/.test(input[i])) {
        num += input[i];
        i++;
      }
      tokens.push({ type: "NUMBER", value: num, pos });
      continue;
    }

    // String literal (double-quoted)
    if (ch === '"') {
      i++; // skip opening quote
      let str = "";
      while (i < input.length && input[i] !== '"') {
        if (input[i] === "\\" && i + 1 < input.length) {
          i++; // skip backslash, take next char
        }
        str += input[i];
        i++;
      }
      if (i >= input.length) throw new FormulaError("Unterminated string", pos);
      i++; // skip closing quote
      tokens.push({ type: "STRING", value: str, pos });
      continue;
    }

    // Field reference: {field_name}
    if (ch === "{") {
      i++; // skip {
      let name = "";
      while (i < input.length && input[i] !== "}") {
        name += input[i];
        i++;
      }
      if (i >= input.length) throw new FormulaError("Unterminated field reference", pos);
      i++; // skip }
      if (!name) throw new FormulaError("Empty field reference", pos);
      tokens.push({ type: "FIELD", value: name, pos });
      continue;
    }

    // Identifier / keyword
    if (/[a-zA-Z_]/.test(ch)) {
      let ident = "";
      while (i < input.length && /[a-zA-Z0-9_]/.test(input[i])) {
        ident += input[i];
        i++;
      }
      const upper = ident.toUpperCase();
      if (upper in KEYWORDS) {
        tokens.push({ type: KEYWORDS[upper], value: upper, pos });
      } else {
        throw new FormulaError(`Unknown identifier "${ident}"`, pos);
      }
      continue;
    }

    throw new FormulaError(`Unexpected character "${ch}"`, pos);
  }

  tokens.push({ type: "EOF", value: "", pos: input.length });
  return tokens;
}

// ---- Parser (recursive descent) ----

class Parser {
  private tokens: Token[];
  private pos = 0;

  constructor(tokens: Token[]) {
    this.tokens = tokens;
  }

  private peek(): Token {
    return this.tokens[this.pos];
  }

  private advance(): Token {
    const tok = this.tokens[this.pos];
    this.pos++;
    return tok;
  }

  private expect(type: TokenType): Token {
    const tok = this.peek();
    if (tok.type !== type) {
      throw new FormulaError(
        `Expected ${type} but got ${tok.type}${tok.value ? ` ("${tok.value}")` : ""}`,
        tok.pos,
      );
    }
    return this.advance();
  }

  parse(): ASTNode {
    const node = this.parseExpression();
    if (this.peek().type !== "EOF") {
      throw new FormulaError(
        `Unexpected token "${this.peek().value}"`,
        this.peek().pos,
      );
    }
    return node;
  }

  private parseExpression(): ASTNode {
    if (this.peek().type === "IF") {
      return this.parseConditional();
    }
    return this.parseComparison();
  }

  private parseConditional(): ASTNode {
    this.expect("IF");
    const condition = this.parseComparison();
    this.expect("THEN");
    const then = this.parseExpression();
    this.expect("ELSE");
    const elseNode = this.parseExpression();
    return { type: "conditional", condition, then, else: elseNode };
  }

  private parseComparison(): ASTNode {
    let left = this.parseAdditive();
    const tok = this.peek();

    // IN operator
    if (tok.type === "IN") {
      this.advance();
      this.expect("LBRACKET");
      const list: ASTNode[] = [];
      if (this.peek().type !== "RBRACKET") {
        list.push(this.parseExpression());
        while (this.peek().type === "COMMA") {
          this.advance();
          list.push(this.parseExpression());
        }
      }
      this.expect("RBRACKET");
      return { type: "in", value: left, list };
    }

    // Comparison operators
    const compOps: Record<string, "=" | "!=" | "<" | ">" | "<=" | ">="> = {
      EQ: "=",
      NEQ: "!=",
      LT: "<",
      GT: ">",
      LTE: "<=",
      GTE: ">=",
    };

    if (tok.type in compOps) {
      const op = compOps[tok.type];
      this.advance();
      const right = this.parseAdditive();
      left = { type: "comparison", op, left, right };
    }

    return left;
  }

  private parseAdditive(): ASTNode {
    let left = this.parseMultiplicative();
    while (this.peek().type === "PLUS" || this.peek().type === "MINUS") {
      const op = this.advance().type === "PLUS" ? "+" : "-";
      const right = this.parseMultiplicative();
      left = { type: "binary", op, left, right } as ASTNode;
    }
    return left;
  }

  private parseMultiplicative(): ASTNode {
    let left = this.parseUnary();
    while (this.peek().type === "STAR" || this.peek().type === "SLASH") {
      const op = this.advance().type === "STAR" ? "*" : "/";
      const right = this.parseUnary();
      left = { type: "binary", op, left, right } as ASTNode;
    }
    return left;
  }

  private parseUnary(): ASTNode {
    if (this.peek().type === "MINUS") {
      this.advance();
      const operand = this.parseUnary();
      return { type: "unary", op: "-", operand };
    }
    return this.parseAtom();
  }

  private parseAtom(): ASTNode {
    const tok = this.peek();

    if (tok.type === "NUMBER") {
      this.advance();
      return { type: "number", value: parseFloat(tok.value) };
    }

    if (tok.type === "STRING") {
      this.advance();
      return { type: "string", value: tok.value };
    }

    if (tok.type === "FIELD") {
      this.advance();
      return { type: "field", name: tok.value };
    }

    if (tok.type === "LPAREN") {
      this.advance();
      const expr = this.parseExpression();
      this.expect("RPAREN");
      return expr;
    }

    throw new FormulaError(
      `Unexpected ${tok.type}${tok.value ? ` ("${tok.value}")` : ""}`,
      tok.pos,
    );
  }
}

// ---- Evaluator ----

function toNumber(val: unknown): number | null {
  if (val === null || val === undefined) return null;
  if (typeof val === "number") return isNaN(val) ? null : val;
  if (typeof val === "string") {
    if (val === "") return null;
    // Strip common formatting: $, commas, whitespace
    const cleaned = val.replace(/[$,\s]/g, "");
    if (cleaned === "") return null;
    const n = Number(cleaned);
    return isNaN(n) ? null : n;
  }
  return null;
}

export function evaluate(ast: ASTNode, data: Record<string, unknown>): unknown {
  switch (ast.type) {
    case "number":
      return ast.value;

    case "string":
      return ast.value;

    case "field": {
      const val = data[ast.name];
      return val === undefined ? null : val;
    }

    case "unary": {
      const operand = evaluate(ast.operand, data);
      const n = toNumber(operand);
      if (n === null) return null;
      return -n;
    }

    case "binary": {
      const left = evaluate(ast.left, data);
      const right = evaluate(ast.right, data);

      // String concatenation with +
      if (ast.op === "+" && (typeof left === "string" || typeof right === "string")) {
        if (left === null || right === null) return null;
        return String(left) + String(right);
      }

      const ln = toNumber(left);
      const rn = toNumber(right);
      if (ln === null || rn === null) return null;

      switch (ast.op) {
        case "+": return ln + rn;
        case "-": return ln - rn;
        case "*": return ln * rn;
        case "/": return rn === 0 ? null : ln / rn;
      }
      break;
    }

    case "comparison": {
      const left = evaluate(ast.left, data);
      const right = evaluate(ast.right, data);
      if (left === null || right === null) return null;

      // Try numeric comparison first
      const lNum = toNumber(left);
      const rNum = toNumber(right);
      if (lNum !== null && rNum !== null) {
        switch (ast.op) {
          case "=":  return lNum === rNum;
          case "!=": return lNum !== rNum;
          case "<":  return lNum < rNum;
          case ">":  return lNum > rNum;
          case "<=": return lNum <= rNum;
          case ">=": return lNum >= rNum;
        }
      }

      // Fall back to string comparison
      const ls = String(left);
      const rs = String(right);
      switch (ast.op) {
        case "=":  return ls === rs;
        case "!=": return ls !== rs;
        case "<":  return ls < rs;
        case ">":  return ls > rs;
        case "<=": return ls <= rs;
        case ">=": return ls >= rs;
      }
      break;
    }

    case "in": {
      const val = evaluate(ast.value, data);
      if (val === null) return null;
      const valStr = String(val);
      for (const item of ast.list) {
        const itemVal = evaluate(item, data);
        if (itemVal !== null && String(itemVal) === valStr) return true;
      }
      return false;
    }

    case "conditional": {
      const cond = evaluate(ast.condition, data);
      if (cond === null) return null;
      // Truthy: true boolean, non-zero number, non-empty string
      const isTruthy = cond === true || (typeof cond === "number" && cond !== 0) || (typeof cond === "string" && cond !== "");
      return isTruthy
        ? evaluate(ast.then, data)
        : evaluate(ast.else, data);
    }
  }

  return null;
}

// ---- Public API ----

/**
 * Parse a formula expression string into an AST.
 * Throws FormulaError on syntax errors.
 */
export function parseExpression(input: string): ASTNode {
  const tokens = tokenize(input.trim());
  const parser = new Parser(tokens);
  return parser.parse();
}

/**
 * Extract all field references from an AST.
 */
export function extractFieldRefs(ast: ASTNode): string[] {
  const refs = new Set<string>();

  function walk(node: ASTNode) {
    switch (node.type) {
      case "field":
        refs.add(node.name);
        break;
      case "unary":
        walk(node.operand);
        break;
      case "binary":
      case "comparison":
        walk(node.left);
        walk(node.right);
        break;
      case "in":
        walk(node.value);
        node.list.forEach(walk);
        break;
      case "conditional":
        walk(node.condition);
        walk(node.then);
        walk(node.else);
        break;
    }
  }

  walk(ast);
  return Array.from(refs);
}

/**
 * Validate an expression string.
 * Returns { valid: true } on success, or { valid: false, error } on failure.
 */
export function validateExpression(
  expr: string,
  availableFields?: string[],
): { valid: true } | { valid: false; error: string } {
  if (!expr.trim()) {
    return { valid: false, error: "Expression is empty" };
  }

  let ast: ASTNode;
  try {
    ast = parseExpression(expr);
  } catch (e) {
    if (e instanceof FormulaError) {
      return { valid: false, error: `${e.message} (at position ${e.position})` };
    }
    return { valid: false, error: String(e) };
  }

  if (availableFields) {
    const fieldSet = new Set(availableFields);
    const refs = extractFieldRefs(ast);
    const unknown = refs.filter((r) => !fieldSet.has(r));
    if (unknown.length > 0) {
      return {
        valid: false,
        error: `Unknown field${unknown.length > 1 ? "s" : ""}: ${unknown.map((f) => `{${f}}`).join(", ")}`,
      };
    }
  }

  return { valid: true };
}
